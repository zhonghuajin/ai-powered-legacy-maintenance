# Set console encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$envFile = ".env"
$pythonScript = "llm_chat.py"

# 1. Check and generate .env file
if (-Not (Test-Path $envFile)) {
    Write-Host "[*] .env file not found. Generating template..." -ForegroundColor Yellow
    
    $envTemplate = @"
# Fill in your API Keys here (leave blank if not needed)
OPENAI_API_KEY=""
DEEPSEEK_API_KEY=""
ZHIPU_API_KEY=""
MOONSHOT_API_KEY=""
DASHSCOPE_API_KEY=""
ANTHROPIC_API_KEY=""
"@
    Set-Content -Path $envFile -Value $envTemplate -Encoding UTF8
    
    Write-Host "[!] .env file generated. Please fill in your API keys and run this script again." -ForegroundColor Green
    exit 1
}

# 2. Check dependencies
$null = python -c "import openai, anthropic, dotenv" 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] Missing dependencies detected. Preparing to install..." -ForegroundColor Cyan
    
    # Check if proxy environment variables are already set
    $proxySet = ($env:HTTP_PROXY -ne $null -and $env:HTTP_PROXY -ne "") -or ($env:HTTPS_PROXY -ne $null -and $env:HTTPS_PROXY -ne "")
    
    if (-Not $proxySet) {
        # Attempt to detect if the user is in Mainland China
        $isChina = $false
        try {
            $country = Invoke-RestMethod -Uri "https://ipinfo.io/country" -TimeoutSec 3 -ErrorAction Stop
            if ($country.Trim() -eq "CN") {
                $isChina = $true
            }
        } catch {
            # Ignore network errors during detection and proceed
        }

        if ($isChina) {
            Write-Host "[!] Mainland China network detected." -ForegroundColor Yellow
            Write-Host "You may need to configure a proxy to install dependencies and access LLM APIs." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Please configure your proxy manually. Example (run these in your terminal):" -ForegroundColor Cyan
            Write-Host "`$env:HTTP_PROXY=`"http://127.0.0.1:7890`"" -ForegroundColor White
            Write-Host "`$env:HTTPS_PROXY=`"http://127.0.0.1:7890`"" -ForegroundColor White
            Write-Host ""
            Write-Host "After configuring the proxy, run this script again." -ForegroundColor Yellow
            Write-Host "Exiting..." -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "[*] Installing required Python packages..." -ForegroundColor Cyan
    
    # Install dependencies, including aiohttp to resolve the langchain conflict
    python -m pip install -q openai anthropic python-dotenv aiohttp
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Error] Failed to install dependencies. Please check your Python/pip environment." -ForegroundColor Red
        Write-Host "Note: If you encounter a 'check_hostname requires server_hostname' error due to your proxy, please upgrade pip first by running:" -ForegroundColor Yellow
        Write-Host "python -m pip install --upgrade pip" -ForegroundColor White
        exit 1
    }
    Write-Host "[*] Dependencies installed successfully!" -ForegroundColor Green
}

# 3. Interactive Provider Selection
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "          Select an LLM Provider        " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  1. DeepSeek"
Write-Host "  2. Claude (Anthropic)"
Write-Host "  3. GPT (OpenAI)"
Write-Host "  4. GLM (Zhipu)"
Write-Host "  5. Kimi (Moonshot)"
Write-Host "  6. Qwen (DashScope)"
Write-Host "========================================" -ForegroundColor Cyan

$provider = ""
while ($provider -eq "") {
    $choice = Read-Host "Enter a number (1-6)"
    switch ($choice) {
        "1" { $provider = "deepseek" }
        "2" { $provider = "claude" }
        "3" { $provider = "gpt" }
        "4" { $provider = "glm" }
        "5" { $provider = "kimi" }
        "6" { $provider = "qwen" }
        default { Write-Host "[!] Invalid input. Please enter a number between 1 and 6." -ForegroundColor Red }
    }
}

# 4. Process arguments (filter out user-provided -p if any, check for file)
$newArgs = @()
$skipNext = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    if ($skipNext) {
        $skipNext = $false
        continue
    }
    # Ignore -p or --provider if passed by habit
    if ($args[$i] -eq "-p" -or $args[$i] -eq "--provider") {
        $skipNext = $true
        continue
    }
    $newArgs += $args[$i]
}

# Prompt for file path if not provided in arguments
if ($newArgs -notcontains "-f" -and $newArgs -notcontains "--file") {
    Write-Host ""
    $filePath = Read-Host "Enter the Markdown file path (e.g., C:\path\to\prompt.md)"
    if ([string]::IsNullOrWhiteSpace($filePath)) {
        Write-Host "[Error] File path cannot be empty. Exiting." -ForegroundColor Red
        exit 1
    }
    $newArgs += "-f"
    $newArgs += $filePath
}

# Add the selected provider to arguments
$newArgs += "-p"
$newArgs += $provider

# 5. Execute Python script
Write-Host ""
Write-Host "[*] Starting request..." -ForegroundColor Cyan
python $pythonScript $newArgs