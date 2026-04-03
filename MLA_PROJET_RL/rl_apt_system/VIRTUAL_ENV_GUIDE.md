# Quick Start Commands for Virtual Environment

## Activate Environment

### Option 1: Using the activation script (easiest)
```cmd
G:\pfe\MLA_PROJET_RL\rl_apt_system\activate_env.bat
```

### Option 2: Manual activation
```cmd
cd G:\pfe\MLA_PROJET_RL\rl_apt_system
venv\Scripts\activate.bat
```

### Option 3: Direct Python execution (no activation needed)
```cmd
G:\pfe\MLA_PROJET_RL\rl_apt_system\venv\Scripts\python.exe train.py --num_episodes 500 --device cuda --output_dir ./outputs
```

---

## Installed Packages

✅ **Core ML/DL:**
- torch 2.9.1 (CUDA support)
- torchvision 0.24.1
- numpy 2.4.1
- pandas 2.3.3

✅ **RL Environment:**
- gymnasium 1.2.3 (modern Gym replacement)

✅ **Visualization:**
- matplotlib 3.10.8
- seaborn 0.13.2

✅ **ML Utilities:**
- scikit-learn 1.8.0
- scipy 1.17.0
- tqdm 4.67.1

✅ **Data Handling:**
- openpyxl 3.1.5

---

## Running Training

### Quick Test (50 episodes, ~5 minutes)
```cmd
venv\Scripts\python.exe train.py --num_episodes 50 --device cpu --output_dir ./quick_test
```

### Full Training (500 episodes, ~30-60 minutes)
```cmd
venv\Scripts\python.exe train.py --num_episodes 500 --device cuda --output_dir ./outputs
```

### Evaluation
```cmd
venv\Scripts\python.exe evaluate.py --agent_path ./outputs/agent_final.pth --num_episodes 100
```

---

## Verify Installation

```cmd
venv\Scripts\python.exe -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

---

## Environment Location

📁 **Virtual Environment:** `G:\pfe\MLA_PROJET_RL\rl_apt_system\venv\`
🐍 **Python:** `3.13.1`
💾 **Size:** ~1.5 GB (with all packages)

---

## Troubleshooting

**If imports fail:**
```cmd
venv\Scripts\pip.exe install --upgrade --force-reinstall gymnasium torch
```

**Check what's installed:**
```cmd
venv\Scripts\pip.exe list
```

**Update requirements:**
```cmd
venv\Scripts\pip.exe install -r requirements.txt
```
