// RL-Based APT Detection System - JavaScript Application

// Global state
let statusCheckInterval = null;
let trainingCheckInterval = null;
let evaluationCheckInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('RL-APT Detection System initialized');
    
    // Setup navigation
    setupNavigation();
    
    // Load initial status
    checkSystemStatus();
    
    // Setup training form
    setupTrainingForm();
    
    // Start periodic status checks
    statusCheckInterval = setInterval(checkSystemStatus, 5000);
    
    // Load model insights
    loadModelInsights();
});

// Navigation
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Remove active class from all links
            navLinks.forEach(l => l.classList.remove('active'));
            
            // Add active class to clicked link
            this.classList.add('active');
            
            // Get tab name
            const tabName = this.dataset.tab;
            
            // Switch tab
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Hide all tabs
    const allTabs = document.querySelectorAll('.tab-content');
    allTabs.forEach(tab => tab.classList.remove('active'));
    
    // Show selected tab
    const selectedTab = document.getElementById(tabName + '-tab');
    if (selectedTab) {
        selectedTab.classList.add('active');
    }
    
    // Update URL hash
    window.location.hash = tabName;
}

// System Status
async function checkSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        // Update model status badges
        updateStatusBadge('ae-status', data.models_available.autoencoder);
        updateStatusBadge('vae-status', data.models_available.vae);
        updateStatusBadge('transformer-status', data.models_available.transformer);
        updateStatusBadge('agent-status', data.models_available.agent);
        
        // Update training status if active
        if (data.training.is_training) {
            updateTrainingProgress(data.training);
        }
        
        // Update evaluation status if active
        if (data.evaluation.is_evaluating) {
            updateEvaluationStatus('Evaluation in progress...');
        } else if (data.evaluation.results) {
            displayEvaluationResults(data.evaluation.results);
        }
        
    } catch (error) {
        console.error('Error checking system status:', error);
    }
}

function updateStatusBadge(elementId, available) {
    const element = document.getElementById(elementId);
    if (element) {
        if (available) {
            element.innerHTML = '<span class="badge bg-success">Ready</span>';
        } else {
            element.innerHTML = '<span class="badge bg-danger">Not Found</span>';
        }
    }
}

// Training
function setupTrainingForm() {
    const form = document.getElementById('training-form');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            await startTraining();
        });
    }
}

async function startTraining() {
    const params = {
        num_episodes: parseInt(document.getElementById('num-episodes').value),
        learning_rate: parseFloat(document.getElementById('learning-rate').value),
        gamma: parseFloat(document.getElementById('gamma').value),
        epsilon_start: parseFloat(document.getElementById('epsilon-start').value),
        epsilon_end: parseFloat(document.getElementById('epsilon-end').value),
        epsilon_decay: parseFloat(document.getElementById('epsilon-decay').value),
        batch_size: parseInt(document.getElementById('batch-size').value)
    };
    
    try {
        const response = await fetch('/api/train', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Show progress container
            document.getElementById('training-progress-container').style.display = 'block';
            document.getElementById('training-status').style.display = 'none';
            
            // Disable start button
            document.getElementById('start-training-btn').disabled = true;
            document.getElementById('start-training-btn').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Training...';
            
            // Start checking training progress more frequently (every 1 second for logs)
            trainingCheckInterval = setInterval(checkTrainingLogs, 1000);
        } else {
            showAlert('training-status', 'danger', data.error);
        }
        
    } catch (error) {
        console.error('Error starting training:', error);
        showAlert('training-status', 'danger', 'Failed to start training');
    }
}

// Check training logs (faster polling for live feedback)
async function checkTrainingLogs() {
    try {
        const response = await fetch('/api/training/logs');
        const data = await response.json();
        
        // Update progress
        updateTrainingProgress(data);
        
    } catch (error) {
        console.error('Error checking training logs:', error);
    }
}

function updateTrainingProgress(trainingData) {
    // Update progress bar
    const progressBar = document.getElementById('training-progress-bar');
    if (progressBar) {
        progressBar.style.width = trainingData.progress + '%';
        progressBar.textContent = trainingData.progress + '%';
    }
    
    // Update stats
    document.getElementById('current-episode').textContent = 
        trainingData.current_episode + ' / ' + trainingData.total_episodes;
    document.getElementById('avg-reward').textContent = 
        trainingData.avg_reward.toFixed(2);
    
    // Update logs
    const logsContainer = document.getElementById('training-logs');
    if (logsContainer && trainingData.logs && trainingData.logs.length > 0) {
        // Show all logs, not just last 20
        logsContainer.innerHTML = trainingData.logs.map(log => 
            '<div class="log-line">' + escapeHtml(log) + '</div>'
        ).join('');
        // Auto-scroll to bottom
        logsContainer.scrollTop = logsContainer.scrollHeight;
    } else if (logsContainer && trainingData.logs && trainingData.logs.length === 0) {
        logsContainer.innerHTML = '<div class="text-warning">Waiting for output...</div>';
    }
    
    // Check if training is complete
    if (!trainingData.is_training && trainingData.progress === 100) {
        document.getElementById('training-state').innerHTML = 
            '<span class="badge bg-success">Complete</span>';
        document.getElementById('start-training-btn').disabled = false;
        document.getElementById('start-training-btn').innerHTML = 
            '<i class="fas fa-play"></i> Start Training';
        clearInterval(trainingCheckInterval);
    }
}

function resetTrainingParams() {
    document.getElementById('num-episodes').value = 100;
    document.getElementById('learning-rate').value = 0.001;
    document.getElementById('gamma').value = 0.99;
    document.getElementById('epsilon-start').value = 1.0;
    document.getElementById('epsilon-end').value = 0.01;
    document.getElementById('epsilon-decay').value = 0.995;
    document.getElementById('batch-size').value = 64;
}

// Evaluation
async function startEvaluation() {
    const agentPath = document.getElementById('agent-path').value;
    const numEpisodes = parseInt(document.getElementById('eval-episodes').value) || 50;
    
    try {
        updateEvaluationStatus('Starting evaluation...');
        
        const response = await fetch('/api/evaluate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                agent_path: agentPath,
                num_episodes: numEpisodes
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            updateEvaluationStatus('Evaluation in progress... This may take several minutes.');
            // Start polling for evaluation logs every 1 second
            evaluationCheckInterval = setInterval(checkEvaluationLogs, 1000);
        } else {
            updateEvaluationStatus(data.error, 'danger');
        }
        
    } catch (error) {
        console.error('Error starting evaluation:', error);
        updateEvaluationStatus('Failed to start evaluation', 'danger');
    }
}

// Check evaluation logs (faster polling for live feedback)
async function checkEvaluationLogs() {
    try {
        const response = await fetch('/api/evaluation/logs');
        const data = await response.json();
        
        // Update progress
        updateEvaluationProgress(data);
        
    } catch (error) {
        console.error('Error checking evaluation logs:', error);
    }
}

function updateEvaluationProgress(evaluationData) {
    // Update progress bar
    const progressBar = document.getElementById('evaluation-progress-bar');
    if (progressBar) {
        progressBar.style.width = evaluationData.progress + '%';
        progressBar.textContent = evaluationData.progress + '%';
    }
    
    // Update stats
    const episodeCounter = document.getElementById('current-eval-episode');
    if (episodeCounter) {
        episodeCounter.textContent = 
            evaluationData.current_episode + ' / ' + evaluationData.total_episodes;
    }
    
    // Update logs
    const logsContainer = document.getElementById('evaluation-logs');
    if (logsContainer && evaluationData.logs && evaluationData.logs.length > 0) {
        logsContainer.innerHTML = evaluationData.logs.map(log => 
            '<div class="log-line">' + escapeHtml(log) + '</div>'
        ).join('');
        // Auto-scroll to bottom
        logsContainer.scrollTop = logsContainer.scrollHeight;
    } else if (logsContainer && evaluationData.logs && evaluationData.logs.length === 0) {
        logsContainer.innerHTML = '<div class="text-warning">Waiting for output...</div>';
    }
    
    // Check if evaluation is complete
    if (!evaluationData.is_evaluating && evaluationData.progress === 100) {
        updateEvaluationStatus('Evaluation complete!', 'success');
        clearInterval(evaluationCheckInterval);
        
        // Display results if available
        if (evaluationData.results) {
            displayEvaluationResults(evaluationData.results);
        }
    }
}

function updateEvaluationStatus(message, type = 'info') {
    const statusDiv = document.getElementById('evaluation-status');
    statusDiv.className = 'alert alert-' + type + ' mt-3';
    statusDiv.innerHTML = '<i class="fas fa-info-circle"></i> ' + message;
}

function displayEvaluationResults(results) {
    if (!results) return;
    
    clearInterval(evaluationCheckInterval);
    
    // Show results container
    document.getElementById('evaluation-results-container').style.display = 'block';
    
    // Update synthetic results
    const synthetic = results.synthetic || {};
    document.getElementById('synthetic-reward').textContent = 
        (synthetic.avg_reward || 0).toFixed(2);
    document.getElementById('synthetic-detection').textContent = 
        ((synthetic.early_detection_rate || 0) * 100).toFixed(1) + '%';
    document.getElementById('synthetic-steps').textContent = 
        (synthetic.avg_steps || 0).toFixed(1);
    
    // Update real results
    const real = results.real || {};
    document.getElementById('real-reward').textContent = 
        (real.avg_reward || 0).toFixed(2);
    document.getElementById('real-detection').textContent = 
        ((real.early_detection_rate || 0) * 100).toFixed(1) + '%';
    document.getElementById('real-steps').textContent = 
        (real.avg_steps || 0).toFixed(1);
    
    // Show evaluation plot
    const plotImg = document.getElementById('evaluation-plot');
    plotImg.src = '/evaluation/evaluation_results.png?' + Date.now();
    
    updateEvaluationStatus('Evaluation complete!', 'success');
}

// Inference
async function runInference() {
    const featuresText = document.getElementById('event-features').value.trim();
    
    if (!featuresText) {
        alert('Please enter event features');
        return;
    }
    
    try {
        const features = JSON.parse(featuresText);
        
        const response = await fetch('/api/inference', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ features: features })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayInferenceResults(data);
        } else {
            alert('Error: ' + data.error);
        }
        
    } catch (error) {
        console.error('Error running inference:', error);
        alert('Invalid JSON or request failed');
    }
}

function displayInferenceResults(data) {
    // Hide placeholder, show results
    document.getElementById('inference-results').style.display = 'none';
    document.getElementById('inference-output').style.display = 'block';
    
    // Autoencoder
    document.getElementById('ae-anomaly-score').textContent = 
        data.autoencoder.anomaly_score.toFixed(3);
    document.getElementById('ae-recon-error').textContent = 
        data.autoencoder.reconstruction_error.toFixed(3);
    document.getElementById('ae-explanation').textContent = 
        data.autoencoder.explanation;
    
    // VAE
    document.getElementById('vae-mal-prob').textContent = 
        (data.vae.malicious_probability * 100).toFixed(1) + '%';
    document.getElementById('vae-uncertainty').textContent = 
        data.vae.uncertainty.toFixed(3);
    document.getElementById('vae-explanation').textContent = 
        data.vae.explanation;
    
    // Agent
    if (data.agent.action) {
        document.getElementById('agent-action-name').textContent = 
            data.agent.action;
        document.getElementById('agent-explanation').textContent = 
            data.agent.explanation;
        
        // Color code based on action
        const actionCard = document.querySelector('.agent-action');
        if (data.agent.action.includes('Monitor')) {
            actionCard.style.borderLeftColor = '#3498db';
        } else if (data.agent.action.includes('Alert')) {
            actionCard.style.borderLeftColor = '#f39c12';
        } else {
            actionCard.style.borderLeftColor = '#e74c3c';
        }
    }
}

function loadSampleEvent() {
    // Generate random sample features (313 dimensions)
    const sampleFeatures = Array.from({length: 313}, () => 
        (Math.random() * 10).toFixed(3)
    );
    document.getElementById('event-features').value = JSON.stringify(sampleFeatures);
}

// Model Insights
async function loadModelInsights() {
    const loadingDiv = document.getElementById('insights-loading');
    const containerDiv = document.getElementById('insights-container');
    
    loadingDiv.style.display = 'block';
    containerDiv.style.display = 'none';
    
    try {
        const response = await fetch('/api/model_insights');
        const data = await response.json();
        
        if (response.ok && data.insights) {
            const tbody = document.getElementById('insights-table-body');
            tbody.innerHTML = data.insights.map(insight => `
                <tr>
                    <td><span class="badge bg-primary">${insight.ckc_stage}</span></td>
                    <td>${insight.stage_name}</td>
                    <td>
                        <div class="progress">
                            <div class="progress-bar bg-danger" style="width: ${insight.anomaly_score * 100}%">
                                ${insight.anomaly_score.toFixed(3)}
                            </div>
                        </div>
                    </td>
                    <td>
                        <div class="progress">
                            <div class="progress-bar bg-warning" style="width: ${insight.malicious_prob * 100}%">
                                ${(insight.malicious_prob * 100).toFixed(1)}%
                            </div>
                        </div>
                    </td>
                    <td><code>#${insight.sample_index}</code></td>
                </tr>
            `).join('');
            
            loadingDiv.style.display = 'none';
            containerDiv.style.display = 'block';
        }
        
    } catch (error) {
        console.error('Error loading model insights:', error);
        loadingDiv.innerHTML = '<p class="text-danger">Failed to load insights</p>';
    }
}

// Reports
async function generateReport(reportType) {
    const statusDiv = document.getElementById('report-status');
    statusDiv.style.display = 'block';
    statusDiv.className = 'alert alert-info mt-3';
    statusDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating PDF report...';
    
    try {
        const response = await fetch('/api/generate_report', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ type: reportType })
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = reportType + '_report.pdf';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            statusDiv.className = 'alert alert-success mt-3';
            statusDiv.innerHTML = '<i class="fas fa-check"></i> Report generated successfully!';
        } else {
            const data = await response.json();
            statusDiv.className = 'alert alert-danger mt-3';
            statusDiv.innerHTML = '<i class="fas fa-times"></i> Error: ' + data.error;
        }
        
    } catch (error) {
        console.error('Error generating report:', error);
        statusDiv.className = 'alert alert-danger mt-3';
        statusDiv.innerHTML = '<i class="fas fa-times"></i> Failed to generate report';
    }
}

// Utility Functions
function showAlert(elementId, type, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.className = 'alert alert-' + type;
        element.innerHTML = '<i class="fas fa-' + 
            (type === 'danger' ? 'exclamation-circle' : 'info-circle') + 
            '"></i> ' + message;
        element.style.display = 'block';
    }
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (statusCheckInterval) clearInterval(statusCheckInterval);
    if (trainingCheckInterval) clearInterval(trainingCheckInterval);
    if (evaluationCheckInterval) clearInterval(evaluationCheckInterval);
});
