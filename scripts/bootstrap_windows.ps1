$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$RequirementsFile = Join-Path $RootDir "requirements.txt"

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Command
    )

    try {
        $output = & $Command[0] @($Command[1..($Command.Length - 1)]) 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) {
            return $output[0].Trim()
        }
    }
    catch {
        return $null
    }

    return $null
}

function Find-InstalledPython {
    $candidates = @()

    $pyExecutable = Test-PythonCommand -Command @("py", "-3", "-c", "import sys; print(sys.executable)")
    if ($pyExecutable) {
        $candidates += $pyExecutable
    }

    $pythonExecutable = Test-PythonCommand -Command @("python", "-c", "import sys; print(sys.executable)")
    if ($pythonExecutable) {
        $candidates += $pythonExecutable
    }

    $searchRoots = @(
        (Join-Path $env:LocalAppData "Programs\Python"),
        (Join-Path $env:ProgramFiles "Python*"),
        (Join-Path ${env:ProgramFiles(x86)} "Python*")
    )

    foreach ($searchRoot in $searchRoots) {
        if (Test-Path $searchRoot) {
            $found = Get-ChildItem -Path $searchRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notlike "*WindowsApps*" } |
                Sort-Object FullName
            $candidates += $found.FullName
        }
    }

    foreach ($candidate in ($candidates | Where-Object { $_ } | Get-Unique)) {
        try {
            & $candidate -c "import sys; print(sys.version)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Install-PythonWithWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }

    Write-Host "[INFO] Python nao encontrado. Instalando Python 3.12 via winget..."
    & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar Python com winget."
    }

    return $true
}

function Ensure-Python {
    $pythonExe = Find-InstalledPython
    if ($pythonExe) {
        return $pythonExe
    }

    $installed = Install-PythonWithWinget
    if ($installed) {
        $pythonExe = Find-InstalledPython
        if ($pythonExe) {
            return $pythonExe
        }
    }

    throw @"
Nao foi possivel localizar um executavel real do Python.
Instale o Python 3.12+ manualmente em https://www.python.org/downloads/windows/
e, se necessario, desabilite os aliases da Microsoft Store em:
Configuracoes > Aplicativos > Configuracoes avancadas de aplicativos > Aliases de execucao do aplicativo
"@
}

$PythonExe = Ensure-Python

Write-Host "[INFO] Python encontrado em: $PythonExe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[INFO] Criando ambiente virtual em .venv..."
    & $PythonExe -m venv (Join-Path $RootDir ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar o ambiente virtual."
    }
}

Write-Host "[INFO] Atualizando pip..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao atualizar o pip."
}

Write-Host "[INFO] Instalando dependencias do projeto..."
& $VenvPython -m pip install -r $RequirementsFile
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao instalar as dependencias do projeto."
}

Write-Host ""
Write-Host "[OK] Ambiente Windows preparado com sucesso."
Write-Host "Proximos comandos:"
Write-Host "  .\.venv\Scripts\python.exe -m pytest -q"
Write-Host "  .\.venv\Scripts\python.exe scripts\demo_real.py"
