$libDir = "c:\Users\Ovindu\Documents\GitHub Fun Projects\TemporalEngine\lib"
if (!(Test-Path $libDir)) { New-Item -ItemType Directory -Path $libDir }

$urls = @(
    "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-flink-runtime-1.18/1.5.2/iceberg-flink-runtime-1.18-1.5.2.jar",
    "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar",
    "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.261/aws-java-sdk-bundle-1.12.261.jar"
)

foreach ($url in $urls) {
    $fileName = [System.IO.Path]::GetFileName($url)
    $dest = Join-Path $libDir $fileName
    if (!(Test-Path $dest)) {
        Write-Host "Downloading $fileName..."
        Invoke-WebRequest -Uri $url -OutFile $dest
    } else {
        Write-Host "$fileName already exists."
    }
}
