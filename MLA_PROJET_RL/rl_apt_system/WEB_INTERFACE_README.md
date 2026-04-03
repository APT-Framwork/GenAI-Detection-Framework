# RL-Based APT Detection System - Web Interface

## 🌐 Modern Web Interface for APT Detection

A beautiful, user-friendly web interface for training, evaluating, and using the Reinforcement Learning-based Advanced Persistent Threat (APT) detection system.

## ✨ Features

### 1. **Dashboard**
- Real-time system status monitoring
- Quick access to all features
- Model availability indicators
- System information overview

### 2. **Training Interface**
- Configure training parameters:
  - Number of episodes
  - Learning rate
  - Discount factor (γ)
  - Epsilon parameters
  - Batch size
- Real-time training progress
- Live logs and metrics
- Training visualizations

### 3. **Evaluation Dashboard**
- Run agent evaluation
- View results for synthetic sequences
- View results for real sequences
- Performance metrics:
  - Average reward
  - Early detection rate
  - Average steps per episode
- Visual charts and graphs

### 4. **Threat Detection (Inference)**
- Real-time threat detection
- Input single events or sequences
- Get predictions from all models:
  - **Autoencoder**: Anomaly scores
  - **VAE**: Malicious probability
  - **Transformer**: Next stage prediction
  - **RL Agent**: Recommended action
- Simple explanations for each model's output

### 5. **Model Insights**
- Understand how models work
- View detection patterns across CKC stages
- Sample-based analysis
- Model architecture details

### 6. **PDF Report Generation**
- Generate professional PDF reports
- Evaluation summaries
- Training history
- Export and share results

## 🚀 Getting Started

### Prerequisites

```bash
# Ensure you're in the virtual environment
cd G:\pfe\MLA_PROJET_RL\rl_apt_system
venv\Scripts\activate
```

### Installation

1. **Install web dependencies:**
```bash
pip install flask werkzeug
```

2. **Optional - For PDF generation:**
```bash
pip install weasyprint
```

### Running the Web Interface

1. **Start the server:**
```bash
python web_app.py
```

2. **Access the interface:**
- Open your browser and navigate to: `http://localhost:5000`
- Or from another device on the same network: `http://<your-ip>:5000`

3. **You should see:**
```
======================================================================
RL-BASED APT DETECTION SYSTEM - WEB INTERFACE
======================================================================

🌐 Starting web server on http://localhost:5000
📊 Access the dashboard at: http://localhost:5000

======================================================================
```

## 📖 Using the Interface

### Training an Agent

1. Navigate to the **Training** tab
2. Configure training parameters:
   - **Episodes**: 100-500 recommended for good performance
   - **Learning Rate**: 0.001 default (adjust if needed)
   - **Gamma**: 0.99 for long-term rewards
   - **Epsilon**: Exploration/exploitation balance
3. Click **"Start Training"**
4. Monitor progress in real-time:
   - Progress bar shows completion
   - View current episode and average reward
   - Watch live training logs

### Evaluating an Agent

1. Navigate to the **Evaluation** tab
2. Verify agent path: `./outputs/agent_final.pth`
3. Click **"Start Evaluation"**
4. Wait for evaluation to complete (may take several minutes)
5. View results:
   - Synthetic sequence performance
   - Real sequence performance
   - Visual plots

### Detecting Threats

1. Navigate to the **Detection** tab
2. Either:
   - Paste your event features (JSON array of 313 values)
   - Click **"Load Sample Event"** for testing
3. Click **"Analyze Event"**
4. View detection results from all models:
   - Anomaly scores
   - Malicious probability
   - Recommended defensive action

### Viewing Model Insights

1. Navigate to the **Model Insights** tab
2. View information about each model:
   - Architecture details
   - Input/output dimensions
   - Purpose and functionality
3. Explore CKC stage analysis table:
   - Sample detection scores per stage
   - Compare model behaviors

### Generating Reports

1. Navigate to the **Reports** tab
2. Choose report type:
   - **Evaluation Report**: Performance metrics and charts
   - **Training Report**: Coming soon
3. Click **"Generate Report"**
4. PDF will download automatically
5. Reports saved in `reports/` directory

## 🎨 Interface Features

### Modern Design
- Gradient backgrounds and smooth animations
- Responsive layout (works on mobile/tablet/desktop)
- Card-based interface for clarity
- Color-coded status indicators

### Real-Time Updates
- Live training progress
- Automatic status checks every 5 seconds
- Dynamic content updates without page refresh

### Interactive Elements
- Hover effects on cards
- Animated progress bars
- Smooth tab transitions
- Visual feedback for actions

## 🔧 Configuration

### Change Port
Edit `web_app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5000)  # Change 5000 to your port
```

### Disable Debug Mode
For production:
```python
app.run(debug=False, host='0.0.0.0', port=5000)
```

### Configure Upload Limits
Edit in `web_app.py`:
```python
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
```

## 📁 Directory Structure

```
rl_apt_system/
├── web_app.py              # Flask backend
├── templates/
│   └── index.html          # Main HTML template
├── static/
│   ├── css/
│   │   └── style.css       # Styling and animations
│   └── js/
│       └── app.js          # JavaScript logic
├── uploads/                # User uploads (created automatically)
├── outputs/                # Agent checkpoints
├── evaluation/             # Evaluation results
└── reports/                # Generated PDF reports
```

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Find and kill process using port 5000
netstat -ano | findstr :5000
taskkill /PID <pid> /F
```

### Models Not Found
- Ensure model files exist in correct directories:
  - `autoencoder_outputs/autoencoder_anomaly_detection.pth`
  - `vae_anomaly_detector_outputs/vae_anomaly_detector.pth`
  - `transformer_outputs/transformer_next_step_prediction.pth`
  - `outputs/agent_final.pth`

### PDF Generation Fails
- Install weasyprint: `pip install weasyprint`
- On Windows, may need GTK+ runtime

### Training Not Starting
- Check that `train.py` exists in the same directory
- Verify virtual environment is activated
- Check console output for error messages

## 🎯 Tips for Best Results

1. **Training**:
   - Start with 100 episodes for testing
   - Use 300-500 episodes for production
   - Monitor average reward - should improve over time

2. **Evaluation**:
   - Run after training completes
   - Compare synthetic vs real sequence performance
   - Early detection rate should be > 0%

3. **Detection**:
   - Test with sample events first
   - Higher anomaly scores = more suspicious
   - Agent actions escalate with threat level

## 📊 Understanding Results

### Good Performance Indicators:
- ✅ Positive average reward
- ✅ Early detection rate > 20%
- ✅ Appropriate action recommendations

### Poor Performance Indicators:
- ❌ Negative average reward (< -10)
- ❌ Early detection rate = 0%
- ❌ NaN values in results

### If Performance is Poor:
1. Increase training episodes (try 500+)
2. Adjust learning rate (try 0.0001 or 0.01)
3. Check data quality in `combined_dataset_final.xlsx`
4. Review reward function in `env/apt_env.py`

## 🔒 Security Notes

- **Development Mode**: Current setup is for development
- **Production**: Disable debug mode and add authentication
- **Network**: Binding to 0.0.0.0 exposes to network
- **Uploads**: Validate all user inputs in production

## 📞 Support

For issues or questions:
1. Check console output for errors
2. Review browser console (F12)
3. Verify all dependencies are installed
4. Ensure models are properly trained

## 🎉 Enjoy!

Your modern, beautiful interface for APT detection is ready! Train agents, detect threats, and generate reports with ease.
