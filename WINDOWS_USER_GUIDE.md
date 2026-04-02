# Windows User Guide: Survivor Trading Strategy

This guide provides step-by-step instructions for setting up and running the Survivor Options Trading Strategy on a Windows laptop.

---

## 1. Prerequisites (One-Time Setup)

### **A. Install Python**
1. Download Python 3.12+ from [python.org](https://www.python.org/downloads/windows/).
2. **Important:** During installation, check the box **"Add Python to PATH"**.

### **B. Install `uv` (Recommended Package Manager)**
Open PowerShell (Search for "PowerShell" in Start menu) and run:
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
*Restart PowerShell after installation.*

---

## 2. Project Setup

### **A. Download and Open the Project**
1. Extract the project files to a folder (e.g., `C:\trading-algo`).
2. Open PowerShell and navigate to the folder:
   ```powershell
   cd C:\trading-algo
   ```

### **B. Install Dependencies**
Run the following command to set up the environment and install all libraries:
```powershell
uv sync
```

### **C. Configure Environment Variables**
1. Copy the sample environment file:
   ```powershell
   copy .sample.env .env
   ```
2. Open `.env` in Notepad and fill in your Dhan credentials:
   ```env
   BROKER_NAME=dhan
   BROKER_ID=YOUR_DHAN_CLIENT_ID
   BROKER_API_KEY=YOUR_DHAN_ACCESS_TOKEN
   ```

---

## 3. How to Run the Scripts

### **A. Running a Backtest**
Before going live, run the backtest to see how the strategy performed historically:
```powershell
uv run python strategy/backtest_survivor.py
```

### **B. Running the Live Strategy**
To start the strategy with your chosen parameters:
```powershell
uv run python strategy/survivor.py `
    --symbol-initials NIFTY25JAN `
    --pe-gap 50 --ce-gap 50 `
    --pe-quantity 75 --ce-quantity 75 `
    --sl-pct 50 --tp-pct 80
```
*(Note: Use the backtick `` ` `` for multi-line commands in PowerShell, or keep it on one line.)*

---

## 4. Maintenance Schedule (What to Change & When)

### **Daily Tasks (Every Morning at 9:00 AM)**
- **Check `.env`:** Ensure your broker API token is still valid.
- **Reference Points:** By default, the script uses the opening price as the reference (`--pe-start-point 0`). You can manually set a specific price if needed.
- **Monitor MTM:** Keep an eye on the console logs for "Daily loss limit breached" warnings.
- **Websocket Connectivity:** Ensure the bot stays connected to the Dhan feed. The strategy now automatically subscribes to new option symbols upon entry for real-time SL/TP tracking.

### **Weekly Tasks (Every Thursday/Friday)**
- **Update `symbol_initials`:** Change the expiry code for the next week's options (e.g., from `NIFTY25JAN` to `NIFTY25FEB`).
- **Review Trades:** Check the `artifacts/orders_data.json` file to see the week's profit/loss.

### **Monthly Tasks**
- **Gap Parameters:** If the market becomes more volatile (VIX > 20), consider increasing `--pe-gap` and `--ce-gap` (e.g., from 50 to 75) to reduce the number of entries and lower risk.
- **Update Instruments:** The bot automatically downloads new instruments, but a restart once a month is good practice.

### **Annual Tasks**
- **Reassess Capital:** Evaluate if your capital has grown enough to increase `--pe-quantity` and `--ce-quantity` to hit your 40-50% annual goal.

---

## 5. Troubleshooting for Windows
- **Execution Policy Error:** If PowerShell blocks the `uv` command, run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- **Module Not Found:** Always use `uv run python` to ensure the script uses the correct environment.

---

**Disclaimer:** Trading involves risk. Always test with small quantities before scaling up.
