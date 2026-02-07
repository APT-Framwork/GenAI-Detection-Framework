"""
RL-Based APT Detection System - Web Interface
==============================================
Modern web interface for training, evaluating, and using the RL agent.
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
from rl.dqn_agent import DQNAgent
from synthetic.conditional_replay import ConditionalReplay

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rl-apt-detection-system-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

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
    # Model paths are in parent directory
    parent_dir = Path(__file__).parent.parent
    
    return jsonify({
        'training': training_status,
        'evaluation': evaluation_status,
        'models_available': {
            'autoencoder': (parent_dir / 'autoencoder_outputs' / 'autoencoder_anomaly_detection.pth').exists(),
            'vae': (parent_dir / 'vae_anomaly_detector_outputs' / 'vae_anomaly_detector.pth').exists(),
            'transformer': (parent_dir / 'transformer_outputs' / 'transformer_next_step_prediction.pth').exists(),
            'agent': os.path.exists('outputs/agent_final.pth')
        }
    })


@app.route('/api/training/logs')
def get_training_logs():
    """Get training logs only (for faster polling)."""
    return jsonify({
        'logs': training_status['logs'][-100:],  # Last 100 lines
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
        'logs': evaluation_status['logs'][-100:],  # Last 100 lines
        'is_evaluating': evaluation_status['is_evaluating'],
        'progress': evaluation_status['progress'],
        'current_episode': evaluation_status['current_episode'],
        'total_episodes': evaluation_status['total_episodes'],
        'results': evaluation_status['results']
    })


@app.route('/api/train', methods=['POST'])
def start_training():
    """Start training the RL agent."""
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
    
    # Reset training status
    training_status['is_training'] = True
    training_status['progress'] = 0
    training_status['current_episode'] = 0
    training_status['total_episodes'] = num_episodes
    training_status['logs'] = []
    training_status['logs'].append('==> Starting training...')
    training_status['logs'].append(f'==> Episodes: {num_episodes}, LR: {learning_rate}, Gamma: {gamma}')
    training_status['logs'].append(f'==> Batch Size: {batch_size}, Device: CPU')
    
    # Start training in background thread
    def run_training():
        try:
            training_status['logs'].append('==> Launching training process...')
            
            cmd = [
                'venv/Scripts/python.exe',
                '-u',  # Run Python in unbuffered mode for real-time output
                'train.py',
                '--num_episodes', str(num_episodes),
                '--learning_rate', str(learning_rate),
                '--gamma', str(gamma),
                '--epsilon_start', str(epsilon_start),
                '--epsilon_end', str(epsilon_end),
                '--epsilon_decay', str(epsilon_decay),
                '--batch_size', str(batch_size),
                '--device', 'cpu',
                '--output_dir', './outputs'
            ]
            
            training_status['logs'].append(f'==> Command: {" ".join(cmd)}')
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            training_status['logs'].append('==> Process started, reading output...')
            
            for line in process.stdout:
                line = line.strip()
                if line:  # Only add non-empty lines
                    training_status['logs'].append(line)
                # Parse progress from output
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
                        reward_str = line.split('Avg Reward')[-1].split(':')[-1].strip()
                        training_status['avg_reward'] = float(reward_str)
                    except:
                        pass
            
            return_code = process.wait()
            
            if return_code == 0:
                training_status['logs'].append('==> Training completed successfully!')
            else:
                training_status['logs'].append(f'==> Training failed with return code: {return_code}')
            
        except Exception as e:
            training_status['logs'].append(f"==> ERROR: {str(e)}")
            import traceback
            training_status['logs'].append(f"==> Traceback: {traceback.format_exc()}")
        finally:
            training_status['is_training'] = False
            training_status['progress'] = 100
            training_status['logs'].append('==> Training process ended')
    
    thread = threading.Thread(target=run_training, daemon=True)
    thread.start()
    
    return jsonify({'message': 'Training started', 'status': 'success'})


@app.route('/api/evaluate', methods=['POST'])
def start_evaluation():
    """Start agent evaluation."""
    if evaluation_status['is_evaluating']:
        return jsonify({'error': 'Evaluation already in progress'}), 400
    
    data = request.json
    agent_path = data.get('agent_path', './outputs/agent_final.pth')
    
    if not os.path.exists(agent_path):
        return jsonify({'error': 'Agent checkpoint not found'}), 404
    
    # Reset evaluation status
    evaluation_status['is_evaluating'] = True
    evaluation_status['progress'] = 0
    evaluation_status['current_episode'] = 0
    evaluation_status['total_episodes'] = data.get('num_episodes', 50)
    evaluation_status['results'] = None
    evaluation_status['logs'] = []
    evaluation_status['logs'].append('==> Starting evaluation...')
    evaluation_status['logs'].append(f'==> Agent path: {agent_path}')
    evaluation_status['logs'].append(f'==> Test episodes: {evaluation_status["total_episodes"]}')
    
    def run_evaluation():
        try:
            evaluation_status['logs'].append('==> Launching evaluation process...')
            
            cmd = [
                'venv/Scripts/python.exe',
                '-u',  # Run Python in unbuffered mode for real-time output
                'evaluate.py',
                '--agent_path', agent_path,
                '--num_episodes', str(evaluation_status['total_episodes'])
            ]
            
            evaluation_status['logs'].append(f'==> Command: {" ".join(cmd)}')
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            evaluation_status['logs'].append('==> Process started, reading output...')
            
            for line in process.stdout:
                line = line.strip()
                if line:  # Only add non-empty lines
                    evaluation_status['logs'].append(line)
                # Parse progress from output
                if 'Episode' in line or 'Testing' in line:
                    try:
                        parts = line.split('/')
                        if len(parts) >= 2:
                            current = int(parts[0].split()[-1])
                            evaluation_status['current_episode'] = current
                            evaluation_status['progress'] = int((current / evaluation_status['total_episodes']) * 100)
                    except:
                        pass
            
            return_code = process.wait()
            
            if return_code == 0:
                evaluation_status['logs'].append('==> Evaluation completed successfully!')
                # Load evaluation results
                results_path = 'evaluation/evaluation_report.json'
                if os.path.exists(results_path):
                    with open(results_path, 'r') as f:
                        evaluation_status['results'] = json.load(f)
                    evaluation_status['logs'].append('==> Results loaded from evaluation_report.json')
            else:
                evaluation_status['logs'].append(f'==> Evaluation failed with return code: {return_code}')
        
        except Exception as e:
            evaluation_status['logs'].append(f"==> ERROR: {str(e)}")
            import traceback
            evaluation_status['logs'].append(f"==> Traceback: {traceback.format_exc()}")
            evaluation_status['results'] = {'error': str(e)}
        finally:
            evaluation_status['is_evaluating'] = False
            evaluation_status['progress'] = 100
            evaluation_status['logs'].append('==> Evaluation process ended')
    
    thread = threading.Thread(target=run_evaluation, daemon=True)
    thread.start()
    
    return jsonify({'message': 'Evaluation started', 'status': 'success'})


@app.route('/api/inference', methods=['POST'])
def run_inference():
    """Run inference on a single event or sequence."""
    try:
        data = request.json
        event_features = np.array(data.get('features', []))
        
        # Load models
        ae_loader = AutoencoderLoader()
        vae_loader = VAELoader()
        transformer_loader = TransformerLoader()
        
        # Pad/truncate features
        if len(event_features) < 313:
            padded = np.zeros(313, dtype=np.float32)
            padded[:len(event_features)] = event_features
            event_features = padded
        else:
            event_features = event_features[:313]
        
        event_features = event_features.reshape(1, -1)
        
        # Get detection signals
        ae_result = ae_loader.get_anomaly_score(event_features)
        vae_result = vae_loader.get_malicious_probability(event_features[:, :191])
        
        # Load agent if available
        agent_action = None
        agent_confidence = None
        
        if os.path.exists('outputs/agent_final.pth'):
            agent = DQNAgent(state_dim=10, action_dim=5)
            agent.load('outputs/agent_final.pth')
            
            # Construct state vector (simplified)
            state = np.array([
                float(ae_result['anomaly_score'][0]),
                float(ae_result['reconstruction_error'][0]),
                float(vae_result['malicious_probability'][0]),
                float(vae_result['uncertainty'][0]),
                0, 0, 0, 0, 0, 0
            ], dtype=np.float32)
            
            action = agent.select_action(state, epsilon=0.0)
            q_values = agent.get_q_values(state)
            
            action_names = {
                0: "Monitor",
                1: "Low Alert",
                2: "Escalate to SOC",
                3: "Isolate Host",
                4: "Block User/IP"
            }
            
            agent_action = action_names[action]
            agent_confidence = float(q_values[action])
        
        return jsonify({
            'autoencoder': {
                'anomaly_score': float(ae_result['anomaly_score'][0]),
                'reconstruction_error': float(ae_result['reconstruction_error'][0]),
                'explanation': 'Measures how unusual this event is compared to normal patterns'
            },
            'vae': {
                'malicious_probability': float(vae_result['malicious_probability'][0]),
                'uncertainty': float(vae_result['uncertainty'][0]),
                'explanation': 'Probability that this event is part of malicious activity'
            },
            'agent': {
                'action': agent_action,
                'confidence': agent_confidence,
                'explanation': f'Recommended defensive action: {agent_action}'
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/model_insights')
def get_model_insights():
    """Get insights from all models."""
    try:
        # Load conditional replay
        replay = ConditionalReplay(real_data_path='combined_dataset_final.xlsx')
        
        # Get sample event from each CKC stage
        insights = []
        
        for stage in [1, 3, 4, 5, 7]:  # Available stages
            try:
                features, idx = replay.sample_event_by_ckc(stage)
                
                # Get model predictions
                ae_loader = AutoencoderLoader()
                vae_loader = VAELoader()
                
                features_reshaped = features.reshape(1, -1)
                ae_result = ae_loader.get_anomaly_score(features_reshaped)
                vae_result = vae_loader.get_malicious_probability(features_reshaped[:, :191])
                
                insights.append({
                    'ckc_stage': f'S{stage}',
                    'stage_name': {
                        1: 'Reconnaissance',
                        3: 'Delivery',
                        4: 'Exploitation',
                        5: 'Installation',
                        7: 'Actions on Objectives'
                    }.get(stage, f'Stage {stage}'),
                    'anomaly_score': float(ae_result['anomaly_score'][0]),
                    'malicious_prob': float(vae_result['malicious_probability'][0]),
                    'sample_index': int(idx)
                })
            except:
                pass
        
        return jsonify({'insights': insights})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate_report', methods=['POST'])
def generate_report():
    """Generate PDF report using reportlab (Windows-compatible)."""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        
        data = request.json
        report_type = data.get('type', 'evaluation')
        
        if report_type == 'evaluation':
            # Load evaluation results
            results_path = 'evaluation/evaluation_report.json'
            if not os.path.exists(results_path):
                return jsonify({'error': 'No evaluation results found'}), 404
            
            with open(results_path, 'r') as f:
                results = json.load(f)
            
            # Generate PDF
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_path = f'reports/evaluation_report_{timestamp}.pdf'
            
            # Create PDF document
            doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                                    rightMargin=72, leftMargin=72,
                                    topMargin=72, bottomMargin=18)
            
            # Container for PDF elements
            elements = []
            
            # Define styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=30,
                alignment=TA_CENTER
            )
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor('#34495e'),
                spaceAfter=12,
                spaceBefore=12
            )
            
            # Title
            elements.append(Paragraph("RL-Based APT Detection System", title_style))
            elements.append(Paragraph("Evaluation Report", heading_style))
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
            elements.append(Spacer(1, 20))
            
            # Synthetic Sequences Results
            elements.append(Paragraph("Synthetic Sequences Results", heading_style))
            synthetic = results.get('synthetic', {})
            syn_data = [
                ['Metric', 'Value'],
                ['Average Reward', f"{synthetic.get('avg_reward', 'N/A'):.2f}" if isinstance(synthetic.get('avg_reward'), (int, float)) else 'N/A'],
                ['Early Detection Rate', f"{synthetic.get('early_detection_rate', 0)*100:.1f}%" if isinstance(synthetic.get('early_detection_rate'), (int, float)) else 'N/A'],
                ['Average Steps', f"{synthetic.get('avg_steps', 'N/A'):.1f}" if isinstance(synthetic.get('avg_steps'), (int, float)) else 'N/A'],
                ['False Positive Rate', f"{synthetic.get('false_positive_rate', 0)*100:.1f}%" if isinstance(synthetic.get('false_positive_rate'), (int, float)) else 'N/A']
            ]
            
            syn_table = Table(syn_data, colWidths=[3*inch, 3*inch])
            syn_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(syn_table)
            elements.append(Spacer(1, 20))
            
            # Real Sequences Results
            elements.append(Paragraph("Real Sequences Results", heading_style))
            real = results.get('real', {})
            real_data = [
                ['Metric', 'Value'],
                ['Average Reward', f"{real.get('avg_reward', 'N/A'):.2f}" if isinstance(real.get('avg_reward'), (int, float)) else 'N/A'],
                ['Early Detection Rate', f"{real.get('early_detection_rate', 0)*100:.1f}%" if isinstance(real.get('early_detection_rate'), (int, float)) else 'N/A'],
                ['Average Steps', f"{real.get('avg_steps', 'N/A'):.1f}" if isinstance(real.get('avg_steps'), (int, float)) else 'N/A'],
                ['False Positive Rate', f"{real.get('false_positive_rate', 0)*100:.1f}%" if isinstance(real.get('false_positive_rate'), (int, float)) else 'N/A']
            ]
            
            real_table = Table(real_data, colWidths=[3*inch, 3*inch])
            real_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(real_table)
            elements.append(Spacer(1, 40))
            
            # Footer
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            elements.append(Paragraph("RL-Based APT Detection System © 2026", footer_style))
            
            # Build PDF
            doc.build(elements)
            
            return send_file(pdf_path, as_attachment=True)
        
        else:
            return jsonify({'error': 'Invalid report type'}), 400
    
    except ImportError as e:
        return jsonify({
            'error': f'reportlab not installed. Install with: pip install reportlab ({str(e)})'
        }), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("\n" + "="*70)
    print("RL-BASED APT DETECTION SYSTEM - WEB INTERFACE")
    print("="*70)
    print("\n🌐 Starting web server on http://localhost:5000")
    print("📊 Access the dashboard at: http://localhost:5000")
    print("\n" + "="*70 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
