# Dumps every cell of the Calendar page's four matrices from the live model, as
#   view|key|sales|orders|band
# for etl/calendar_expected.py --compare to diff against pandas.
#
# Each view is queried the way its matrix sees the page: the Day view under a Month and a Year
# pinned with TREATAS (all 48 months in turn), the Month view under a Year, the Quarter and Year
# views under nothing. The bands come from [Cal Band ...], so ALLSELECTED is resolving against
# the same outer filters the slicers would apply.
#
#   powershell -File etl/verify_calendar.ps1 > calendar_dump.txt
#   python etl/calendar_expected.py --compare calendar_dump.txt
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

$inv = [Globalization.CultureInfo]::InvariantCulture

function Dump($view, $dax) {
    $cmd = $conn.CreateCommand()
    $cmd.CommandTimeout = 300
    $cmd.CommandText = $dax
    $r = $cmd.ExecuteReader()
    while ($r.Read()) {
        $key = $r.GetValue(0)
        if ($key -is [datetime]) { $key = $key.ToString("yyyy-MM-dd") }
        $s = $r.GetValue(1); $o = $r.GetValue(2); $b = $r.GetValue(3)
        $sTxt = if ($s -is [DBNull] -or $null -eq $s) { "0" } else { ([double]$s).ToString("0.00", $inv) }
        $oTxt = if ($o -is [DBNull] -or $null -eq $o) { "0" } else { "$o" }
        $bTxt = if ($b -is [DBNull] -or $null -eq $b) { "" } else { "$b" }
        Write-Output "$view|$key|$sTxt|$oTxt|$bTxt"
    }
    $r.Close()
}

$months = "January","February","March","April","May","June","July","August","September","October","November","December"
$watch = [Diagnostics.Stopwatch]::StartNew()

foreach ($y in 2021..2024) {
    foreach ($mName in $months) {
        Dump "Day" @"
EVALUATE
CALCULATETABLE(
    SELECTCOLUMNS(
        SUMMARIZE('Date', 'Date'[Date], 'Date'[Week of Month], 'Date'[Day Short]),
        "k", 'Date'[Date], "s", [Sales], "o", [Orders], "b", [Cal Band Day]
    ),
    TREATAS({"$mName"}, 'Date'[Month]), TREATAS({$y}, 'Date'[Year])
)
"@
    }
    Dump "Month" @"
EVALUATE
CALCULATETABLE(
    SELECTCOLUMNS(
        SUMMARIZE('Date', 'Date'[Month No], 'Date'[Quarter], 'Date'[Month in Quarter]),
        "k", "$y-" & FORMAT('Date'[Month No], "00"), "s", [Sales], "o", [Orders], "b", [Cal Band Month]
    ),
    TREATAS({$y}, 'Date'[Year])
)
"@
}

Dump "Quarter" @"
EVALUATE
SELECTCOLUMNS(
    SUMMARIZE('Date', 'Date'[Quarter Year Sort], 'Date'[Year], 'Date'[Quarter]),
    "k", 'Date'[Year] & "-" & 'Date'[Quarter], "s", [Sales], "o", [Orders], "b", [Cal Band Quarter]
)
"@

Dump "Year" @"
EVALUATE
SELECTCOLUMNS(VALUES('Date'[Year]), "k", FORMAT('Date'[Year], "0"), "s", [Sales], "o", [Orders], "b", [Cal Band Year])
"@

Write-Output ("# done in {0} ms" -f $watch.ElapsedMilliseconds)
$conn.Close()
