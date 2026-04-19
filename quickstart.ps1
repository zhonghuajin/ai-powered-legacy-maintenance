<#
.SYNOPSIS
    Instrumentor Test Bug Fix Workflow Quickstart Script
.DESCRIPTION
    This script guides you through the full process of code instrumentation, compiling and running the instrumentor test, log denoising and analysis, AI prompt generation, and automated bug fixing.
#>

# Helper function to print a prominent pause prompt
function Pause-ForNextStep {
    param (
        [string]$CompletedStep,
        [string]$NextStep
    )
    Write-Host ""
    Write-Host "*****************************************************************" -ForegroundColor Yellow
    if (![string]::IsNullOrEmpty($CompletedStep)) {
        Write-Host "   $CompletedStep completed!" -ForegroundColor Green
    }
    Write-Host "   👉 Press [Enter] to continue to $NextStep ..." -ForegroundColor Yellow
    Write-Host "*****************************************************************" -ForegroundColor Yellow
    Read-Host
}

$workDir = $PWD.Path
$instrumentorTestPath = Join-Path $workDir "core\instrumentor-test"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "      Instrumentor Test Workflow Quickstart Script     " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "Current working directory: $workDir"
Write-Host "Source and runtime path: $instrumentorTestPath"
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------
# 🐛 BUG DEMONSTRATION & DISCLAIMER INFO
# ---------------------------------------------------------
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
Write-Host " 🐛 BUG DEMONSTRATION INFO & DISCLAIMER:" -ForegroundColor Yellow
Write-Host " This workflow uses the sample code located in: " -NoNewline -ForegroundColor Yellow
Write-Host "core\instrumentor-test" -ForegroundColor Cyan
Write-Host ""
Write-Host " [The Pre-set Bug]" -ForegroundColor Yellow
Write-Host " There is an intentional concurrency bug in 'Test 8: Event-Driven Aggregation'." -ForegroundColor Yellow
Write-Host " Symptom: The final output array is [0, 0, 0] instead of the expected [500, 1000, 1500]." -ForegroundColor Yellow
Write-Host " Root Cause: A Happens-Before violation where the main thread reads the results" -ForegroundColor Yellow
Write-Host "             before the async EventBus finishes writing them." -ForegroundColor Yellow
Write-Host ""
Write-Host " [Disclaimer]" -ForegroundColor Yellow
Write-Host " Modern LLMs are incredibly powerful. Even without this project's methodology," -ForegroundColor Yellow
Write-Host " they can easily spot this specific bug just by reading the static source code." -ForegroundColor Yellow
Write-Host " Therefore, this Quickstart is NOT meant to prove the superiority of this tool" -ForegroundColor Yellow
Write-Host " on simple bugs. Instead, it serves as a sandbox to demonstrate the GENERAL WORKFLOW:" -ForegroundColor Yellow
Write-Host "   1. Code Instrumentation" -ForegroundColor Yellow
Write-Host "   2. Execution & Log Generation" -ForegroundColor Yellow
Write-Host "   3. Log Denoising" -ForegroundColor Yellow
Write-Host "   4. AI Prompt Generation" -ForegroundColor Yellow
Write-Host "   5. Ask LLM for Bug Localization" -ForegroundColor Yellow
Write-Host "   6. Generate Fix Prompt" -ForegroundColor Yellow
Write-Host "   7. Ask LLM for Code Fix" -ForegroundColor Yellow
Write-Host "   8. Apply Fix to Source Code" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------" -ForegroundColor Yellow
Write-Host ""

# ---------------------------------------------------------
# Check current Java version (requires >= 17)
# ---------------------------------------------------------
$isValidJdk = $false
$currentVersion = "Unknown"

try {
    # java -version output is typically on stderr, capture with 2>&1
    $javaVersionOutput = java -version 2>&1
    foreach ($line in $javaVersionOutput) {
        # Match patterns like version "17.0.1" or version "1.8.0"
        if ($line -match 'version "(\d+)') {
            $majorVersion = [int]$matches[1]
            
            # Handle Java 8 and earlier (e.g., 1.8.x extracts 1)
            if ($majorVersion -eq 1) {
                if ($line -match 'version "1\.(\d+)') {
                    $currentVersion = "1.$([int]$matches[1])"
                }
            } else {
                $currentVersion = $majorVersion
            }

            if ($majorVersion -ge 17) {
                $isValidJdk = $true
            }
            break
        }
    }
} catch {
    Write-Host "Java command not detected in environment variables." -ForegroundColor Yellow
}

if ($isValidJdk) {
    Write-Host "[Environment Check] System Java version is $currentVersion, meets requirement (>= 17), skipping path configuration." -ForegroundColor Green
} else {
    if ($currentVersion -ne "Unknown") {
        Write-Host "[Environment Check] System Java version is $currentVersion, lower than required JDK 17." -ForegroundColor Yellow
    } else {
        Write-Host "[Environment Check] No valid Java environment detected." -ForegroundColor Yellow
    }
    
    Write-Host "Please ensure you have JDK 17 or higher installed." -ForegroundColor Yellow
    $jdkPath = Read-Host "Enter the installation path of JDK (>=17) (e.g., C:\Program Files\Java\jdk-17) [Press Enter to skip]"
    
    if (![string]::IsNullOrWhiteSpace($jdkPath)) {
        $env:JAVA_HOME = $jdkPath
        $env:Path = "$env:JAVA_HOME\bin;$env:Path"
        Write-Host "Temporarily added the specified JDK to environment variables." -ForegroundColor Green
    } else {
        Write-Host "No path entered. Will attempt to use current environment; this may cause compilation or runtime failures." -ForegroundColor Red
    }
}

# ---------------------------------------------------------
# Pre-check: Ensure .env exists for LLM steps later
# ---------------------------------------------------------
$askLlmDir = Join-Path $workDir "enginerring\ask-llm"
$envFile = Join-Path $askLlmDir ".env"

if (-Not (Test-Path $envFile)) {
    Write-Host "`n[*] Pre-flight check: .env file not found for LLM steps. Generating template..." -ForegroundColor Yellow
    
    if (-Not (Test-Path $askLlmDir)) {
        New-Item -ItemType Directory -Force -Path $askLlmDir | Out-Null
    }
    
    $envTemplate = @"
# 请在此处填入你需要的 API Key (不需要的可以留空)
OPENAI_API_KEY=""
DEEPSEEK_API_KEY=""
ZHIPU_API_KEY=""
MOONSHOT_API_KEY=""
DASHSCOPE_API_KEY=""
ANTHROPIC_API_KEY=""
"@
    Set-Content -Path $envFile -Value $envTemplate -Encoding UTF8
    
    Write-Host "[!] .env file generated at: $envFile" -ForegroundColor Green
    Write-Host "[!] Please fill in your API keys in the generated .env file and run this quickstart script again." -ForegroundColor Red
    exit 1
} else {
    Write-Host "[Environment Check] LLM .env file found." -ForegroundColor Green
}

# ---------------------------------------------------------
# Pre-check: Select LLM Provider for the workflow
# ---------------------------------------------------------
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

$llmChoice = ""
while ($llmChoice -notmatch "^[1-6]$") {
    $llmChoice = Read-Host "Enter a number (1-6) for the LLM Provider to use throughout this workflow"
    if ($llmChoice -notmatch "^[1-6]$") {
        Write-Host "[!] Invalid input. Please enter a number between 1 and 6." -ForegroundColor Red
    }
}
Write-Host "[Environment Check] LLM Provider selected: Option $llmChoice" -ForegroundColor Green

Pause-ForNextStep -CompletedStep "[Environment Setup]" -NextStep "[Step 0] Setup Shadow Branch"

# ---------------------------------------------------------
# Step 0 & 1. Setup Shadow Branch and Instrument Code
# ---------------------------------------------------------
Write-Host "`n>>> [Step 0 & 1] Setting up shadow branch and instrumenting code..." -ForegroundColor Cyan

# 提示用户输入目标 Git 根目录
$gitRootDir = Read-Host "Please enter the target Git root directory for the instrumentation project"
while ([string]::IsNullOrWhiteSpace($gitRootDir)) {
    Write-Host "[!] Path cannot be empty." -ForegroundColor Red
    $gitRootDir = Read-Host "Please enter the target Git root directory"
}

# 提示用户选择插桩模式
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       Select Instrumentation Mode      " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  1. Full Instrumentation (全量插桩)"
Write-Host "  2. Incremental Instrumentation (增量插桩)"
Write-Host "========================================" -ForegroundColor Cyan

$instModeChoice = ""
while ($instModeChoice -notmatch "^[1-2]$") {
    $instModeChoice = Read-Host "Enter a number (1-2) for the instrumentation mode"
    if ($instModeChoice -notmatch "^[1-2]$") {
        Write-Host "[!] Invalid input. Please enter 1 or 2." -ForegroundColor Red
    }
}

$modeArg = if ($instModeChoice -eq "1") { "full" } else { "incremental" }
Write-Host "[Mode Selection] Selected mode: $modeArg" -ForegroundColor Green

# 更新为新的脚本名称
$setupScriptPath = Join-Path $workDir "enginerring/shadow-project-management/instrument_with_shadow_project.py"

if (Test-Path $setupScriptPath) {
    Write-Host "Executing: python instrument_with_shadow_project.py `"$gitRootDir`" --mode $modeArg"
    python $setupScriptPath "$gitRootDir" --mode $modeArg
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to setup shadow branch and instrument code. Exiting." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} else {
    Write-Host "Warning: instrument_with_shadow_project.py not found at $setupScriptPath." -ForegroundColor Yellow
    Write-Host "Please ensure the script is placed in the correct directory. Exiting." -ForegroundColor Red
    exit 1
}

Pause-ForNextStep -CompletedStep "[Step 0 & 1] Setup Shadow Branch & Instrumentation" -NextStep "[Step 2] Compile and Run Instrumentor Test"

# ---------------------------------------------------------
# Step 2. Compile and Run the Reproducer (Instrumentor Test)
# ---------------------------------------------------------
Write-Host "`n>>> [Step 2] Compiling and running instrumentor test..." -ForegroundColor Cyan
Set-Location $instrumentorTestPath

Write-Host "Executing: mvn clean package -DskipTests"
mvn clean package -DskipTests

Write-Host "Executing: java -jar target\instrumentor-test-1.0-SNAPSHOT.jar"
java -jar target\instrumentor-test-1.0-SNAPSHOT.jar

Write-Host "Program execution finished. Please verify that instrumentor-events-*.txt and instrumentor-log-*.txt have been generated in $instrumentorTestPath" -ForegroundColor Green

Pause-ForNextStep -CompletedStep "[Step 2] Compile and Run" -NextStep "[Step 3] Analyze Logs and Extract Denoised Data"

# ---------------------------------------------------------
# Step 3. Analyze Logs to Extract Denoised Data
# ---------------------------------------------------------
Write-Host "`n>>> [Step 3] Analyzing logs and extracting denoised data..." -ForegroundColor Cyan
Set-Location $workDir

# Automatically locate the latest log files
$logFile = Get-ChildItem -Path $instrumentorTestPath -Filter "instrumentor-log-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$eventsFile = Get-ChildItem -Path $instrumentorTestPath -Filter "instrumentor-events-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($logFile -and $eventsFile) {
    Write-Host "Found log file: $($logFile.FullName)"
    Write-Host "Found events file: $($eventsFile.FullName)"
    
    .\process-logs-demo.ps1 `
        -TargetFoldersFile ".\target-folders.txt" `
        -LogFile $logFile.FullName `
        -CommentMappingFile ".\comment-mapping.txt" `
        -EventsFile $eventsFile.FullName
} else {
    Write-Host "Could not find generated log or events file. Please check if Step 2 executed successfully and generated the logs." -ForegroundColor Red
}

Pause-ForNextStep -CompletedStep "[Step 3] Log Analysis" -NextStep "[Step 4] Generate AI Prompt"

# ---------------------------------------------------------
# Step 4. Generate the AI Prompt
# ---------------------------------------------------------
Write-Host "`n>>> [Step 4] Generating AI Prompt..." -ForegroundColor Cyan

# Ensure we are in the original working directory
Set-Location $workDir

$aiAppPath = Join-Path $workDir "core\denoised-data-ai-app"
$pythonScriptPath = Join-Path $aiAppPath "generate_bug_localization_prompt.py"

if (Test-Path $pythonScriptPath) {
    Write-Host "Running Python script from $workDir to generate the prompt automatically with option [2]..." -ForegroundColor Green
    
    # Construct the path to the combined file generated in Step 3
    $combinedFilePath = Join-Path $workDir "final-output-combined.md"
    
    # Provide interactive inputs sequentially using an array
    $aiInputs = @(
        "2",                # 1. Select Analysis Mode: 2 (Include Concurrency Analysis)
        "The event-driven aggregation test incorrectly outputs an array of zeros instead of the expected computed values because the program retrieves the results before the background tasks have finished processing them.",                 # 2. Observable Symptom: (Leave empty to skip)
        "",                 # 3. Tech Stack Context: (Leave empty to skip)
        "",                 # 4. Additional Notes: (Leave empty to skip)
        $combinedFilePath,  # 5. Call Tree File With Concurrency: Provide the exact absolute path
        ""                  # 6. Extra Enter to prevent any trailing prompts
    )
    
    # Pipe the array to the Python script using its full path
    $aiInputs | python $pythonScriptPath
} else {
    Write-Host "AI Prompt generation script not found at: $pythonScriptPath" -ForegroundColor Red
}

Pause-ForNextStep -CompletedStep "[Step 4] Generate AI Prompt" -NextStep "[Step 5] Ask LLM for Bug Localization"

# ---------------------------------------------------------
# Step 5. Ask LLM for Bug Localization
# ---------------------------------------------------------
Write-Host "`n>>> [Step 5] Asking LLM for Bug Localization..." -ForegroundColor Cyan

# Check for System Proxy Settings
$proxyRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
$proxyEnable = (Get-ItemProperty -Path $proxyRegPath -Name ProxyEnable -ErrorAction SilentlyContinue).ProxyEnable

if ($proxyEnable -eq 1) {
    $proxyServer = (Get-ItemProperty -Path $proxyRegPath -Name ProxyServer -ErrorAction SilentlyContinue).ProxyServer
    if (![string]::IsNullOrWhiteSpace($proxyServer)) {
        # Handle formats like "http=127.0.0.1:7890;https=127.0.0.1:7890" or just "127.0.0.1:7890"
        $proxyAddress = $proxyServer
        if ($proxyServer -match "http=([^;]+)") {
            $proxyAddress = $matches[1]
        }
        
        # Ensure it has http:// prefix
        if ($proxyAddress -notmatch "^http(s)?://") {
            $proxyAddress = "http://$proxyAddress"
        }

        $env:HTTP_PROXY = $proxyAddress
        $env:HTTPS_PROXY = $proxyAddress
        Write-Host "[Proxy Check] Detected system proxy is enabled." -ForegroundColor Yellow
        Write-Host "Automatically configured HTTP_PROXY and HTTPS_PROXY to: $proxyAddress" -ForegroundColor Green
    }
} else {
    Write-Host "[Proxy Check] No system proxy detected. Skipping proxy configuration." -ForegroundColor DarkGray
}

# Move into ask-llm directory and stay there for the rest of the script
$askLlmDir = Join-Path $workDir "enginerring\ask-llm"
Set-Location $askLlmDir

$localizationPromptPath = Join-Path $workDir "AI_Bug_Localization_Prompt.md"

if (Test-Path ".\run.ps1") {
    $llmInputs1 = @(
        $llmChoice,             # 1. Select LLM Provider (User's choice from the beginning)
        $localizationPromptPath # 2. Markdown file path
    )
    # 将 .\run.ps1 替换为调用 powershell.exe
    $llmInputs1 | powershell.exe -ExecutionPolicy Bypass -File ".\run.ps1"
} else {
    Write-Host "run.ps1 not found in $askLlmDir" -ForegroundColor Red
}

Pause-ForNextStep -CompletedStep "[Step 5] Ask LLM for Bug Localization" -NextStep "[Step 6] Generate Fix Prompt"

# ---------------------------------------------------------
# Step 6. Generate the Fix Prompt
# ---------------------------------------------------------
Write-Host "`n>>> [Step 6] Generating Fix Prompt..." -ForegroundColor Cyan

$fixBugDir = Join-Path $workDir "enginerring\fix-bug"
$generateFixScript = Join-Path $fixBugDir "generate_fix_prompt.py"

if (Test-Path $generateFixScript) {
    $fixPromptInputs = @(
        "output.md",        # 1. Path to diagnostic report (located in current ask-llm dir)
        $targetFoldersFile  # 2. Path to base directories (target-folders.txt)
    )
    $fixPromptInputs | python $generateFixScript
} else {
    Write-Host "generate_fix_prompt.py not found at: $generateFixScript" -ForegroundColor Red
}

Pause-ForNextStep -CompletedStep "[Step 6] Generate Fix Prompt" -NextStep "[Step 7] Ask LLM for Code Fix"

# ---------------------------------------------------------
# Step 7. Ask LLM for Code Fix
# ---------------------------------------------------------
Write-Host "`n>>> [Step 7] Asking LLM for Code Fix..." -ForegroundColor Cyan

if (Test-Path ".\run.ps1") {
    $llmInputs2 = @(
        $llmChoice,                # 1. Select LLM Provider (User's choice from the beginning)
        "AI_Apply_Fix_Prompt.md"   # 2. Markdown file path
    )
    # 同样替换为调用 powershell.exe
    $llmInputs2 | powershell.exe -ExecutionPolicy Bypass -File ".\run.ps1"
} else {
    Write-Host "run.ps1 not found in $askLlmDir" -ForegroundColor Red
}

Pause-ForNextStep -CompletedStep "[Step 7] Ask LLM for Code Fix" -NextStep "[Step 8] Apply Fix to Source Code"

# ---------------------------------------------------------
# Step 8. Apply Fix to Source Code
# ---------------------------------------------------------
Write-Host "`n>>> [Step 8] Applying Fix to Source Code..." -ForegroundColor Cyan

$applyFixScript = Join-Path $fixBugDir "apply_fix.py"

if (Test-Path $applyFixScript) {
    $applyFixInputs = @(
        "output.md",        # 1. Path to fixed code (overwritten in current ask-llm dir)
        $targetFoldersFile  # 2. Path to base directories
    )
    $applyFixInputs | python $applyFixScript
} else {
    Write-Host "apply_fix.py not found at: $applyFixScript" -ForegroundColor Red
}

Write-Host "`n=======================================================" -ForegroundColor Magenta
Write-Host "  🎉 Workflow execution completed! The bug has been fixed." -ForegroundColor Green
Write-Host "  You can now re-run the tests to verify the fix." -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Magenta

Set-Location $workDir