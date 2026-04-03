@echo off
REM Activation script for RL APT Detection System
REM Usage: Run this file before training

echo ========================================
echo  RL APT Detection System
echo  Activating Virtual Environment
echo ========================================
echo.

cd /d G:\pfe\MLA_PROJET_RL\rl_apt_system

call venv\Scripts\activate.bat

echo.
echo ✓ Virtual environment activated!
echo.
echo Python version:
python --version
echo.
echo Installed packages:
pip list | findstr "torch numpy gym"
echo.
echo ========================================
echo  Ready to train!
echo  Run: python train.py --num_episodes 500 --device cuda --output_dir ./outputs
echo ========================================
echo.

cmd /k
