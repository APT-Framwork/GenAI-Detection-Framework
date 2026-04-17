"""
RL-Based APT Detection System - Web Interface
==============================================
Modern web interface for training, evaluating, and using the RL agent.
Updated for 25-feature models with GNN integration and model selection.
"""

import os
import json
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import numpy as np
import pandas as pd

# Import system components
from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from models.gnn_loader import GNNLoader
from rl.dqn_agent import DQNAgent

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rl-apt-detection-system-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# Global state
training_status = {
    'is_training': False,
    'progress': 0,
    'current_episode': 0,
    'total_episodes': 0,
    'avg_reward': 0.0,
    'logs': []
}

evaluation_status = {
    'is_evaluating': False,
    'progress': 0,
    'current_episode': 0,
    'total_episodes': 0,
    'results': None,
    'logs': []
}

# Ensure directories exist
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path('outputs').mkdir(exist_ok=True)
Path('evaluation').mkdir(exist_ok=True)
Path('reports').mkdir(exist_ok=True)


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Get system status."""
    parent_dir = Path(__file__).parent.parent
    models_dir = parent_dir / 'models'

    return jsonify({
        'training': training_status,
        'evaluation': evaluation_status,
        'models_available': {
            'autoencoder_64': (models_dir / 'reg_ae_top25_features.pth').exists(),
            'autoencoder_32': (models_dir / 'reg_ae_top25_features_32dim.pth').exists(),
            'beta_vae': (models_dir / 'beta_vae_top25_features.pth').exists(),
            'beta_vae_32': (models_dir / 'beta_vae_top25_features_32dim.pth').exists(),
            'beta_vae_malicious': (models_dir / 'beta_vae_malicious_only_32dim.pth').exists(),
            'transformer': (models_dir / 'transformer_next_step_prediction_top25.pth').exists(),
            'gnn': (models_dir / 'gnn_propagation_best_no_rule.pth').exists(),
            'agent': os.path.exists('outputs/agent_final.pth') or os.path.exists('outputs/agent_best.pth'),
        },
        'model_variants': {
            'ae_options': [
                {'key': 'reg_ae_64', 'label': 'Regularized AE (latent=64)', 'available': (models_dir / 'reg_ae_top25_features.pth').exists()},
                {'key': 'reg_ae_32', 'label': 'Regularized AE (latent=32)', 'available': (models_dir / 'reg_ae_top25_features_32dim.pth').exists()},
            ],
            'vae_options': [
                {'key': 'beta_vae', 'label': 'Beta-VAE (all data)', 'available': (models_dir / 'beta_vae_top25_features.pth').exists()},
                {'key': 'beta_vae_32', 'label': 'Beta-VAE 32dim', 'available': (models_dir / 'beta_vae_top25_features_32dim.pth').exists()},
                {'key': 'beta_vae_malicious', 'label': 'Beta-VAE (malicious only)', 'available': (models_dir / 'beta_vae_malicious_only_32dim.pth').exists()},
            ],
        }
    })


@app.route('/api/training/logs')
def get_training_logs():
    """Get training logs only (for faster polling)."""
    return jsonify({
        'logs': training_status['logs'][-100:],
        'is_training': training_status['is_training'],
        'progress': training_status['progress'],
        'current_episode': training_status['current_episode'],
        'total_episodes': training_status['total_episodes'],
        'avg_reward': training_status['avg_reward']
    })


@app.route('/api/evaluation/logs')
def get_evaluation_logs():
    """Get evaluation logs only (for faster polling)."""
    return jsonify({
        'logs': evaluation_status['logs'][-100:],
        'is_evaluating': evaluation_status['is_evaluating'],
        'progress': evaluation_status['progress'],
        'current_episode': evaluation_status['current_episode'],
        'total_episodes': evaluation_status['total_episodes'],
        'results': evaluation_status['results']
    })


@app.route('/api/train', methods=['POST'])
def start_training():
    """Start training the RL agent with model selection."""
    if training_status['is_training']:
        return jsonify({'error': 'Training already in progress'}), 400

    data = request.json
    num_episodes = data.get('num_episodes', 100)
    learning_rate = data.get('learning_rate', 0.001)
    gamma = data.get('gamma', 0.99)
    epsilon_start = data.get('epsilon_start', 1.0)
    epsilon_end = data.get('epsilon_end', 0.01)
    epsilon_decay = data.get('epsilon_decay', 0.995)
    batch_size = data.get('batch_size', 64)
    ae_variant = data.get('ae_variant', 'reg_ae_64')
    vae_variant = data.get('vae_variant', 'beta_vae')
    data_source = data.get('data_source', 'synthetic')

    # Reset training status
    training_status['is_training'] = True
    training_status['progress'] = 0
    training_status['current_episode'] = 0
    training_status['total_episodes'] = num_episodes
    training_status['logs'] = []
    training_status['logs'].append('==> Starting training...')
    training_status['logs'].append(f'==> AE: {ae_variant}, VAE: {vae_variant}')
    training_status['logs'].append(f'==> Episodes: {num_episodes}, LR: {learning_rate}, Data: {data_source}')

    def run_training():
        try:
            training_status['logs'].append('==> Launching training process...')

            # Find python executable
            python_exe = 'python'
            if os.path.exists('venv/Scripts/python.exe'):
                python_exe = 'venv/Scripts/python.exe'

            cmd = [
                python_exe, '-u', 'train.py',
                '--num_episodes', str(num_episodes),
                '--learning_rate', str(learning_rate),
                '--gamma', str(gamma),
                '--epsilon_start', str(epsilon_start),
                '--epsilon_end', str(epsilon_end),
                '--epsilon_decay', str(epsilon_decay),
                '--batch_size', str(batch_size),
                '--ae_variant', ae_variant,
                '--vae_variant', vae_variant,
                '--data_source', data_source,
                '--device', 'cpu',
                '--output_dir', './outputs',
            ]

            training_status['logs'].append(f'==> Command: {" ".join(cmd)}')

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, bufsize=1
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    training_status['logs'].append(line)
                if 'Episode' in line:
                    try:
                        parts = line.split('/')
                        if len(parts) >= 2:
                            current = int(parts[0].split()[-1])
                            training_status['current_episode'] = current
                            training_status['progress'] = int((current / num_episodes) * 100)
                    except:
                        pass
                if 'Avg Reward' in line:
                    try:
                        reward_str = line.split('Avg Reward:')[-1].split('|')[0].strip()
                        training_status['avg_reward'] = float(reward_str)
                    except:
                        pass

            return_code = process.wait()
            if return_code == 0:
                training_status['logs'].append('==> Training completed successfully!')
            else:
                training_status['logs'].append(f'==> Training failed with code: {return_code}')

        except Exception as e:
            training_status['logs'].append(f"==> ERROR: {str(e)}")
            import traceback
            training_status['logs'].append(f"==> {traceback.format_exc()}")
        finally:
            training_status['is_training'] = False
            training_status['progress'] = 100

    thread = threading.Thread(target=run_training, daemon=True)
    thread.start()

    return jsonify({'message': 'Training started', 'status': 'success'})


@app.route('/api/evaluate', methods=['POST'])
def start_evaluation():
    """Start agent evaluation."""
    if evaluation_status['is_evaluating']:
        return jsonify({'error': 'Evaluation already in progress'}), 400

    data = request.json
    agent_path = data.get('agent_path', './outputs/agent_best.pth')
    ae_variant = data.get('ae_variant', 'reg_ae_64')
    vae_variant = data.get('vae_variant', 'beta_vae')

    if not os.path.exists(agent_path):
        # Try alternate path
        if os.path.exists('./outputs/agent_final.pth'):
            agent_path = './outputs/agent_final.pth'
        else:
            return jsonify({'error': 'Agent checkpoint not found'}), 404

    evaluation_status['is_evaluating'] = True
    evaluation_status['progress'] = 0
    evaluation_status['total_episodes'] = data.get('num_episodes', 50)
    evaluation_status['results'] = None
    evaluation_status['logs'] = [f'==> Evaluating: {agent_path}']

    def run_evaluation():
        try:
            python_exe = 'python'
            if os.path.exists('venv/Scripts/python.exe'):
                python_exe = 'venv/Scripts/python.exe'

            cmd = [
                python_exe, '-u', 'evaluate.py',
                '--agent_path', agent_path,
                '--num_episodes', str(evaluation_status['total_episodes']),
                '--ae_variant', ae_variant,
                '--vae_variant', vae_variant,
            ]

            evaluation_status['logs'].append(f'==> Command: {" ".join(cmd)}')

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, bufsize=1
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    evaluation_status['logs'].append(line)

            process.wait()

            results_path = 'evaluation/evaluation_report.json'
            if os.path.exists(results_path):
                with open(results_path, 'r') as f:
                    evaluation_status['results'] = json.load(f)
                evaluation_status['logs'].append('==> Results loaded')

        except Exception as e:
            evaluation_status['logs'].append(f"==> ERROR: {str(e)}")
        finally:
            evaluation_status['is_evaluating'] = False
            evaluation_status['progress'] = 100

    thread = threading.Thread(target=run_evaluation, daemon=True)
    thread.start()

    return jsonify({'message': 'Evaluation started', 'status': 'success'})


@app.route('/api/inference', methods=['POST'])
def run_inference():
    """Run inference on a single event."""
    try:
        data = request.json
        event_features = np.array(data.get('features', []), dtype=np.float32)
        ae_variant = data.get('ae_variant', 'reg_ae_64')
        vae_variant = data.get('vae_variant', 'beta_vae')

        # Load models
        ae_loader = AutoencoderLoader(variant=ae_variant)
        vae_loader = VAELoader(variant=vae_variant)

        # Pad/truncate to 55
        if len(event_features) < 55:
            padded = np.zeros(55, dtype=np.float32)
            padded[:len(event_features)] = event_features
            event_features = padded
        else:
            event_features = event_features[:55]

        event_features = event_features.reshape(1, -1)

        # Get detection signals
        ae_result = ae_loader.get_anomaly_score(event_features)
        vae_result = vae_loader.get_malicious_probability(event_features)

        # Load agent if available
        agent_action = None
        agent_confidence = None

        for agent_file in ['outputs/agent_best.pth', 'outputs/agent_final.pth']:
            if os.path.exists(agent_file):
                from env.apt_env import APTEnvironment
                agent = DQNAgent(state_dim=APTEnvironment.STATE_DIM, action_dim=5)
                agent.load(agent_file)

                state = np.zeros(APTEnvironment.STATE_DIM, dtype=np.float32)
                state[0] = float(ae_result['anomaly_score'][0])
                state[1] = float(ae_result['reconstruction_error'][0])
                state[2] = float(vae_result['malicious_probability'][0])
                state[3] = float(vae_result['uncertainty'][0])

                action = agent.select_action(state, epsilon=0.0)
                q_values = agent.get_q_values(state)

                agent_action = APTEnvironment.ACTION_NAMES[action]
                agent_confidence = float(q_values[action])
                break

        return jsonify({
            'autoencoder': {
                'anomaly_score': float(ae_result['anomaly_score'][0]),
                'reconstruction_error': float(ae_result['reconstruction_error'][0]),
            },
            'vae': {
                'malicious_probability': float(vae_result['malicious_probability'][0]),
                'uncertainty': float(vae_result['uncertainty'][0]),
            },
            'agent': {
                'action': agent_action,
                'confidence': agent_confidence,
            },
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate_report', methods=['POST'])
def generate_report():
    """Generate PDF report."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        results_path = 'evaluation/evaluation_report.json'
        if not os.path.exists(results_path):
            return jsonify({'error': 'No evaluation results found'}), 404

        with open(results_path, 'r') as f:
            results = json.load(f)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_path = f'reports/evaluation_report_{timestamp}.pdf'

        doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)

        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                     fontSize=24, textColor=colors.HexColor('#2c3e50'),
                                     spaceAfter=30, alignment=TA_CENTER)
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
                                       fontSize=16, textColor=colors.HexColor('#34495e'),
                                       spaceAfter=12, spaceBefore=12)

        elements.append(Paragraph("RL-Based APT Detection System", title_style))
        elements.append(Paragraph("Evaluation Report (25-Feature Models + GNN)", heading_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        for source_name, source_key in [('Synthetic', 'synthetic'), ('Real', 'real')]:
            source_data = results.get(source_key, {})
            if not source_data:
                continue

            elements.append(Paragraph(f"{source_name} Sequences Results", heading_style))
            rows = [
                ['Metric', 'Value'],
                ['Avg Reward', f"{source_data.get('avg_reward', 0):.2f}"],
                ['Precision', f"{source_data.get('precision', 0):.3f}"],
                ['Recall', f"{source_data.get('recall', 0):.3f}"],
                ['F1 Score', f"{source_data.get('f1', 0):.3f}"],
                ['Early Detection Rate', f"{source_data.get('early_detection_rate', 0)*100:.1f}%"],
                ['False Positive Rate', f"{source_data.get('false_positive_rate', 0)*100:.1f}%"],
            ]

            table = Table(rows, colWidths=[3*inch, 3*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))

        doc.build(elements)
        return send_file(pdf_path, as_attachment=True)

    except ImportError as e:
        return jsonify({'error': f'reportlab not installed: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("RL-BASED APT DETECTION SYSTEM - WEB INTERFACE")
    print("=" * 70)
    print("\n🌐 Starting web server on http://localhost:5000")
    print("📊 Access the dashboard at: http://localhost:5000")
    print("\n" + "=" * 70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
