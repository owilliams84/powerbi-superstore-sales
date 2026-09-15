# Queries the live model for every figure on the Revenue page, for one year and comparison.
#
# The answer key is etl/revenue_expected.py, which gets the same figures from the CSVs in pandas.
# TREATAS pins the year and each button slicer the way the page does, so these are the numbers
# the cards, tables and titles resolve to.
#
#   powershell -File etl/verify_revenue.ps1 -Year 2024 -Comparison "Prior year"
#
# Run as a background job - closing the ADOMD connection can hang the shell.

param(
    [int]$Year = 2024,
    [string]$Comparison = "Prior year"
)

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
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $r = $cmd.ExecuteReader()
    $names = @(); for ($i = 0; $i -lt $r.FieldCount; $i++) { $names += $r.GetName($i) }
    Write-Output ("   " + ($names -join " | "))
    while ($r.Read()) {
        $vals = @()
        for ($i = 0; $i -lt $r.FieldCount; $i++) {
            $v = $r.GetValue($i)
            if ($v -is [double]) { $v = [math]::Round($v, 2) }
            $vals += "$v"
        }
        Write-Output ("   " + ($vals -join " | "))
    }
    $r.Close()
    Write-Output ("   ({0} ms)" -f $watch.ElapsedMilliseconds)
}

$pin = "TREATAS({$Year}, 'Date'[Year]), TREATAS({""$Comparison""}, Comparison[Comparison])"

Invoke-Dax "Headline: $Year against '$Comparison'" @"
EVALUATE
CALCULATETABLE(
    ROW(
        "Comparison year", [Comparison Year],
        "Sales", [Sales], "Comparison", [Sales Comparison], "Change %", [Sales vs Comparison %],
        "Orders", [Orders], "Orders comp", [Orders Comparison],
        "AOV", [Average Order Value], "AOV comp", [Average Order Value Comparison],
        "Customers above", [Customers Above Comparison], "In play", [Customers In Play],
        "Regions above", [Regions Above Comparison],
        "Sub-cats above", [Sub-categories Above Comparison], "Sub-cats in play", [Sub-categories In Play]
    ),
    $pin
)
"@

Invoke-Dax "Monthly change and running totals" @"
EVALUATE
SUMMARIZECOLUMNS(
    'Date'[Month No], $pin,
    "Change", [Sales vs Comparison],
    "Cumulative", CALCULATE([Sales Line], TREATAS({"Cumulative"}, 'Line View'[View])),
    "Cumulative comp", CALCULATE([Comparison Line], TREATAS({"Cumulative"}, 'Line View'[View]))
)
ORDER BY 'Date'[Month No]
"@

foreach ($show in @("Top", "Bottom")) {
    Invoke-Dax "Customers, $show 8" @"
EVALUATE
FILTER(
    SUMMARIZECOLUMNS(
        Customer[Customer], $pin, TREATAS({"$show"}, 'Customer Ranking'[Show]),
        "Rank", [Customer Change Rank], "Sales", [Sales], "Comp", [Sales Comparison],
        "Change", [Sales vs Comparison]
    ),
    [Rank] <= 8
)
ORDER BY [Rank]
"@
    Invoke-Dax "Sub-categories, $show 8" @"
EVALUATE
FILTER(
    SUMMARIZECOLUMNS(
        'Product'[Sub-Category], $pin, TREATAS({"$show"}, 'Sub-category Ranking'[Show]),
        "Rank", [Sub-category Change Rank], "Change", [Sales vs Comparison]
    ),
    [Rank] <= 8
)
ORDER BY [Rank]
"@
}

Invoke-Dax "Titles" @"
EVALUATE
CALCULATETABLE(
    UNION(
        ROW("Text", [Title Standfirst]),
        ROW("Text", [Title Line Chart] & " / " & [Subtitle Line Chart]),
        ROW("Text", [Subtitle Variance Chart]),
        ROW("Text", [Title Customer Table] & " / " & [Subtitle Customer Table]),
        ROW("Text", [Title Sub-category Table] & " / " & [Subtitle Sub-category Table]),
        ROW("Text", [Filter Summary])
    ),
    $pin
)
"@

Invoke-Dax "SVG measures: length and head" @"
EVALUATE
CALCULATETABLE(
    UNION(
        ROW("Measure", "Card Sales", "Length", LEN([Card Sales]), "Head", LEFT([Card Sales], 90)),
        ROW("Measure", "Card Customers", "Length", LEN([Card Customers]), "Head", LEFT([Card Customers], 90)),
        ROW("Measure", "Card Regions", "Length", LEN([Card Regions]), "Head", LEFT([Card Regions], 90)),
        ROW("Measure", "Card Sub-categories", "Length", LEN([Card Sub-categories]), "Head", LEFT([Card Sub-categories], 90))
    ),
    $pin
)
"@

$conn.Close()
