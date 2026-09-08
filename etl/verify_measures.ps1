# Queries the live model over XMLA and prints the numbers the report puts on screen.
#
# Reading figures off a screenshot proves the visual rendered, not that it is right. This asks the
# engine directly, so the output can be checked against etl/verify_expected.py, which computes the
# same figures from the CSVs with no DAX involved.
#
#   powershell -File etl/verify_measures.ps1
#
# Run as a background job - closing the ADOMD connection can hang the shell.

$ErrorActionPreference = "Stop"

$msmdsrv = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe'"
if (-not $msmdsrv) { throw "msmdsrv.exe is not running - open the PBIP in Desktop first." }
$port = $null
foreach ($proc in $msmdsrv) {
    $conn = Get-NetTCPConnection -State Listen -OwningProcess $proc.ProcessId -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -eq "127.0.0.1" } | Select-Object -First 1
    if ($conn) { $port = $conn.LocalPort; break }
}
if (-not $port) { throw "could not find the local XMLA port" }

$pkg = (Get-AppxPackage -Name "*PowerBIDesktop*").InstallLocation
$adomd = @("Microsoft.PowerBI.AdomdClient.dll", "Microsoft.AnalysisServices.AdomdClient.dll") |
         ForEach-Object { Join-Path $pkg "bin\$_" } |
         Where-Object { Test-Path $_ } | Select-Object -First 1
[void][Reflection.Assembly]::LoadFrom($adomd)

$probe = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
$probe.Open()
$c = $probe.CreateCommand()
$c.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
$rd = $c.ExecuteReader(); $catalog = $null
if ($rd.Read()) { $catalog = $rd.GetString(0) }
$rd.Close(); $probe.Close()

$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection(
    "Data Source=localhost:$port;Initial Catalog=$catalog")
$conn.Open()

function Invoke-Dax($label, $dax) {
    Write-Output ""
    Write-Output "== $label"
    $cmd = $conn.CreateCommand()
    $cmd.CommandTimeout = 300
    $cmd.CommandText = $dax
    $r = $cmd.ExecuteReader()
    $names = @(); for ($i = 0; $i -lt $r.FieldCount; $i++) { $names += $r.GetName($i) }
    Write-Output ("   " + ($names -join " | "))
    while ($r.Read()) {
        $vals = @()
        for ($i = 0; $i -lt $r.FieldCount; $i++) {
            $v = $r.GetValue($i)
            if ($v -is [double]) { $v = [math]::Round($v, 4) }
            $vals += "$v"
        }
        Write-Output ("   " + ($vals -join " | "))
    }
    $r.Close()
}

# TREATAS pins the year exactly as a slicer would, so these are the numbers the cards and charts
# resolve to - not a different query that happens to agree.
Invoke-Dax "Headline, whole period" @"
EVALUATE
ROW(
    "Sales", [Sales], "Orders", [Orders], "Customers", [Customers],
    "AOV", [Average Order Value], "Products sold", [Products Sold],
    "Period", [Report Period]
)
"@

Invoke-Dax "By year: sales, PY, YoY, orders, new, returning" @"
EVALUATE
SUMMARIZECOLUMNS(
    'Date'[Year],
    "Sales", [Sales], "PY", [Sales PY], "YoY", [Sales YoY %],
    "Orders", [Orders], "New", [New Customers], "Returning", [Returning Customers]
)
ORDER BY 'Date'[Year]
"@

Invoke-Dax "Category share, whole period" @"
EVALUATE
SUMMARIZECOLUMNS('Product'[Category], "Sales", [Sales], "Share", [Sales Share])
ORDER BY [Sales] DESC
"@

Invoke-Dax "Sub-categories 2024, top 5 with cumulative share" @"
EVALUATE
TOPN(5,
    SUMMARIZECOLUMNS('Product'[Sub-Category], TREATAS({2024}, 'Date'[Year]),
        "Sales", [Sales], "Cumulative", [Cumulative Sales Share]),
    [Sales], DESC)
ORDER BY [Sales] DESC
"@

Invoke-Dax "Customer KPIs, whole period: repeat share, active every year" @"
EVALUATE ROW("Repeat share", [Repeat Customer Share], "Every year", [Customers Active Every Year])
"@

Invoke-Dax "Cohort retention" @"
EVALUATE
SUMMARIZECOLUMNS(Customer[Cohort], 'Date'[Year], "Size", [Cohort Size], "Retention", [Retention %])
ORDER BY Customer[Cohort], 'Date'[Year]
"@

Invoke-Dax "Ship mode, whole period" @"
EVALUATE
SUMMARIZECOLUMNS('Ship Mode'[Ship Mode], "Share of orders", [Ship Mode Share], "Days", [Average Ship Days])
ORDER BY 'Ship Mode'[Ship Mode]
"@

Invoke-Dax "Standard Class share by region (KEEPFILTERS check - must differ by row)" @"
EVALUATE
SUMMARIZECOLUMNS(Geography[Region], "Standard share", [Standard Class Share])
ORDER BY Geography[Region]
"@

Invoke-Dax "Top states 2024" @"
EVALUATE
TOPN(3,
    SUMMARIZECOLUMNS(Geography[State], TREATAS({2024}, 'Date'[Year]),
        "Rank", [State Rank], "Sales", [Sales], "Share", [Sales Share]),
    [Sales], DESC)
ORDER BY [Sales] DESC
"@

Invoke-Dax "Top product, whole period" @"
EVALUATE
TOPN(1, SUMMARIZECOLUMNS('Product'[Product], "Sales", [Sales]), [Sales], DESC)
"@

$conn.Close()
