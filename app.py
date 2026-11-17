from flask import Flask, request, jsonify, send_from_directory, send_file
import requests
import json
import sys
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

app = Flask(__name__, static_folder='.', static_url_path='')

# Allowed file extensions (for validation only)
ALLOWED_SPEC_EXTENSIONS = {'json', 'yaml', 'yml', 'txt', 'md'}

# Maximum file size (16 MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename, allowed_extensions):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions



def invoke_evaluation(spec_content, supporting_docs=""):
    """Run the local LangGraph and adapt its structured result for the UI."""
    from root_agent.agent import evaluate_api

    try:
        result = evaluate_api(spec_content, supporting_docs)
        content = json.dumps(result["results"], ensure_ascii=False, indent=2)
        return 200, {"raw_response": content, "results": result["results"], "summary": result["summary"]}
    except (ValueError, RuntimeError) as exc:
        return 400, {"error": str(exc)}
    except Exception as exc:
        print(f"LangGraph evaluation failed: {exc}")
        return 500, {"error": "Evaluation failed. Check model credentials and server logs."}


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file upload and trigger AI evaluation"""
    try:
        print(f"\n{'='*60}")
        print("NEW UPLOAD REQUEST")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        # Log request details
        print(f"Request method: {request.method}")
        print(f"Request content type: {request.content_type}")
        print(f"Files in request: {list(request.files.keys())}")
        sys.stdout.flush()

        # Validate files are present
        if 'apiSpecification' not in request.files:
            print("ERROR: API Specification file is missing from request")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': 'API Specification file is missing'
            }), 400

        api_spec_file = request.files['apiSpecification']
        supporting_doc_file = request.files.get('supportingDocuments')
        print(f"API Spec file object: {api_spec_file}")
        print(f"API Spec filename: {api_spec_file.filename}")
        sys.stdout.flush()

        # Check if file is selected
        if api_spec_file.filename == '':
            print("ERROR: No API Specification file selected")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': 'No API Specification file selected'
            }), 400

        # Validate file extension
        if not allowed_file(api_spec_file.filename, ALLOWED_SPEC_EXTENSIONS):
            print(f"ERROR: Invalid file extension: {api_spec_file.filename}")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': f'Invalid API Specification file type. Allowed: {", ".join(ALLOWED_SPEC_EXTENSIONS)}'
            }), 400

        # Read file content directly (no storage)
        print("Reading file content...")
        sys.stdout.flush()
        spec_content = api_spec_file.read().decode('utf-8')
        supporting_docs = ""
        if supporting_doc_file and supporting_doc_file.filename:
            if not allowed_file(supporting_doc_file.filename, {'txt', 'md'}):
                return jsonify({'success': False, 'message': 'Supporting examples must be a .txt or .md file'}), 400
            supporting_docs = supporting_doc_file.read().decode('utf-8')
        print(f"\nAPI Spec file received: {api_spec_file.filename}")
        print(f"Content length: {len(spec_content)} bytes")
        sys.stdout.flush()

        # Run the in-process LangGraph evaluation.
        print("\n" + "="*60)
        print("Starting AI agent evaluation...")
        print("="*60)
        sys.stdout.flush()

        status_code, agent_response = invoke_evaluation(spec_content, supporting_docs)

        print(f"\nAgent invocation completed")
        print(f"Status code: {status_code}")
        print(f"Response type: {type(agent_response)}")
        sys.stdout.flush()

        if status_code != 200 or agent_response is None:
            print(f"ERROR: Agent evaluation failed with status {status_code}")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': agent_response.get('error', 'AI agent evaluation failed') if isinstance(agent_response, dict) else 'AI agent evaluation failed'
            }), status_code

        print("\n✓ Agent evaluation completed successfully!")
        print(f"Response keys: {agent_response.keys() if isinstance(agent_response, dict) else 'N/A'}")
        sys.stdout.flush()

        print(f"\n{'='*60}")
        print("REQUEST COMPLETED SUCCESSFULLY")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        # Return agent response directly to UI
        response_data = {
            'success': True,
            'message': 'Evaluation completed successfully',
            'agentResponse': agent_response,
            'fileName': api_spec_file.filename
        }

        print("Sending response to client...")
        sys.stdout.flush()

        return jsonify(response_data), 200

    except Exception as e:
        print(f"\n{'!'*60}")
        print(f"EXCEPTION in upload_files: {str(e)}")
        print(f"{'!'*60}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

        return jsonify({
            'success': False,
            'message': f'Error processing upload: {str(e)}'
        }), 500


@app.route('/upload-from-github', methods=['POST'])
def upload_from_github():
    """Handle GitHub repository file fetching and trigger AI evaluation"""
    try:
        print(f"\n{'='*60}")
        print("NEW GITHUB FETCH REQUEST")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        # Get GitHub parameters from request
        data = request.json
        github_url = (data.get('githubUrl') or '').strip()
        yaml_path = (data.get('yamlPath') or '').strip()
        prompts_path = (data.get('promptsPath') or '').strip()
        branch = (data.get('branch') or 'main').strip()

        print(f"GitHub URL: {github_url}")
        print(f"YAML Path: {yaml_path}")
        print(f"Prompts Path: {prompts_path or 'None'}")
        print(f"Branch: {branch}")
        sys.stdout.flush()

        # Validate required fields
        if not github_url or not yaml_path:
            print("ERROR: Missing GitHub URL or YAML path")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': 'GitHub URL and YAML file path are required'
            }), 400

        # Parse GitHub URL to extract owner and repo
        # Example: https://github.com/username/repo or https://github.com/username/repo.git
        try:
            github_url = github_url.rstrip('/').replace('.git', '')
            parts = github_url.split('/')
            if len(parts) < 2:
                raise ValueError("Invalid GitHub URL format")
            owner = parts[-2]
            repo = parts[-1]
            print(f"Parsed - Owner: {owner}, Repo: {repo}")
            sys.stdout.flush()
        except Exception as e:
            print(f"ERROR: Failed to parse GitHub URL: {e}")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': f'Invalid GitHub URL format. Expected: https://github.com/username/repository'
            }), 400

        # Fetch YAML file from GitHub
        print(f"\nFetching YAML file from GitHub...")
        sys.stdout.flush()
        yaml_content = fetch_github_file(owner, repo, yaml_path, branch)

        if not yaml_content:
            print("ERROR: Failed to fetch YAML file from GitHub")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': f'Failed to fetch YAML file from GitHub. Please check the repository URL, file path, and branch name.'
            }), 400

        print(f"✓ YAML file fetched successfully ({len(yaml_content)} bytes)")
        sys.stdout.flush()

        supporting_docs = ""
        prompts_content = None
        # Fetch prompts file if provided
        if prompts_path:
            print(f"\nFetching prompts file from GitHub...")
            sys.stdout.flush()
            prompts_content = fetch_github_file(owner, repo, prompts_path, branch)

            if prompts_content:
                supporting_docs = prompts_content
            else:
                print(f"⚠ Warning: Could not fetch prompts file (optional, continuing...)")
                sys.stdout.flush()

        # Run the in-process LangGraph evaluation.
        print("\n" + "="*60)
        print("Starting AI agent evaluation...")
        print("="*60)
        sys.stdout.flush()

        status_code, agent_response = invoke_evaluation(yaml_content, supporting_docs)

        print(f"\nAgent invocation completed")
        print(f"Status code: {status_code}")
        print(f"Response type: {type(agent_response)}")
        sys.stdout.flush()

        if status_code != 200 or agent_response is None:
            print(f"ERROR: Agent evaluation failed with status {status_code}")
            sys.stdout.flush()
            return jsonify({
                'success': False,
                'message': agent_response.get('error', 'AI agent evaluation failed') if isinstance(agent_response, dict) else 'AI agent evaluation failed'
            }), status_code

        print("\n✓ Agent evaluation completed successfully!")
        sys.stdout.flush()

        print(f"\n{'='*60}")
        print("GITHUB FETCH REQUEST COMPLETED SUCCESSFULLY")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        # Return agent response directly to UI
        response_data = {
            'success': True,
            'message': 'Evaluation completed successfully',
            'agentResponse': agent_response,
            'fileName': yaml_path
        }

        print("Sending response to client...")
        sys.stdout.flush()

        return jsonify(response_data), 200

    except Exception as e:
        print(f"\n{'!'*60}")
        print(f"EXCEPTION in upload_from_github: {str(e)}")
        print(f"{'!'*60}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

        return jsonify({
            'success': False,
            'message': f'Error processing GitHub request: {str(e)}'
        }), 500


def fetch_github_file(owner, repo, file_path, branch='main'):
    Fetch a file from GitHub repository using raw content URL

    Args:
        owner: GitHub repository owner
        repo: Repository name
        file_path: Path to file in repository
        branch: Branch name (default: main)

    Returns:
        File content as string, or None if failed
    """
    try:
        # Construct raw GitHub URL
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        print(f"Fetching from: {url}")
        sys.stdout.flush()

        response = requests.get(url, timeout=30)

        if response.status_code == 404:
            # Try master branch if main doesn't exist
            print(f"File not found on '{branch}' branch, trying 'master'...")
            sys.stdout.flush()
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{file_path}"
            print(f"Fetching from: {url}")
            sys.stdout.flush()
            response = requests.get(url, timeout=30)

        if response.status_code == 200:
            print(f"✓ File fetched successfully")
            sys.stdout.flush()
            return response.text
        else:
            print(f"✗ Failed to fetch file: HTTP {response.status_code}")
            sys.stdout.flush()
            return None

    except requests.exceptions.Timeout:
        print(f"✗ Timeout while fetching file from GitHub")
        sys.stdout.flush()
        return None
    except Exception as e:
        print(f"✗ Error fetching GitHub file: {str(e)}")
        sys.stdout.flush()
        return None


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'Server is running',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def index():
    """Serve the index.html file"""
    return send_file('index.html')


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """Serve static assets"""
    return send_from_directory('assets', filename)



@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    return jsonify({
        'success': False,
        'message': 'File too large. Maximum size is 16MB'
    }), 413


def _wrap_text_for_pdf(text, max_width, pdf_canvas, font_name, font_size):
    words = text.split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _build_report_text(results, title, summary=None):
    lines = [title, ""]
    if summary:
        lines.extend([
            f"Overall score: {summary.get('final_score', 'N/A')} / 10",
            f"Readiness tier: {summary.get('tier', 'N/A')} - {summary.get('tier_description', '')}",
            "",
        ])
        for item in summary.get('score_breakdown', []):
            lines.append(
                f"{item.get('label', item.get('type', 'Assessment'))}: "
                f"{item.get('score', 'N/A')} / 10 "
                f"(weight {float(item.get('weight', 0)):.0%})"
            )
        lines.append("")
    for idx, item in enumerate(results, start=1):
        item_type = item.get('type', 'Unknown')
        score = item.get('score', 'N/A')
        lines.append(f"{idx}. {item_type} - Score {score}")

        analysis = item.get('analysis', {})
        if isinstance(analysis, dict):
            for key, value in analysis.items():
                label = key.replace('_', ' ').title()
                lines.append(f"   {label}: {value}")

        recommendations = item.get('recommendations', [])
        if recommendations:
            lines.append("   Recommendations:")
            for rec in recommendations:
                lines.append(f"     - {rec}")

        lines.append("")
    return "\n".join(lines)


def _generate_pdf_bytes(report_text, title):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 0.75 * inch
    y = height - margin

    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin, y, title)
    y -= 18

    font_name = "Helvetica"
    font_size = 10
    pdf.setFont(font_name, font_size)
    max_width = width - (2 * margin)

    for paragraph in report_text.split("\n"):
        if paragraph.strip() == "":
            y -= font_size * 1.2
            continue
        for line in _wrap_text_for_pdf(paragraph, max_width, pdf, font_name, font_size):
            if y < margin:
                pdf.showPage()
                y = height - margin
                pdf.setFont(font_name, font_size)
            pdf.drawString(margin, y, line)
            y -= font_size * 1.2

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    """Generate a PDF report from structured results or raw text."""
    try:
        data = request.json or {}
        title = (data.get('title') or 'API Agentic Readiness Report').strip()
        results = data.get('results')
        summary = data.get('summary')
        raw_text = (data.get('rawText') or '').strip()

        if not results and not raw_text:
            return jsonify({
                'success': False,
                'message': 'No report content provided'
            }), 400

        if results:
            report_text = _build_report_text(results, title, summary)
        else:
            report_text = raw_text

        pdf_bytes = _generate_pdf_bytes(report_text, title)
        return send_file(
            pdf_bytes,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='agentic-readiness-report.pdf'
        )
    except Exception as e:
        print(f"ERROR: Failed to generate PDF: {e}")
        sys.stdout.flush()
        return jsonify({
            'success': False,
            'message': 'Failed to generate PDF report'
        }), 500


if __name__ == '__main__':
    print("\n" + "="*50)
    print("Flask Server Starting (Simplified - No File Storage)")
    print("="*50)
    print("Server running at: http://localhost:8080")
    print("LangGraph evaluator runs in-process")
    print("="*50 + "\n")

    # Run the Flask app
    app.run(host='127.0.0.1', port=8080, debug=False)

