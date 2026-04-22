$clips_dir = "dataset\CCTV Footage"
$layout = "dataset\store_layout.json"
$start_utc = "2026-10-04T14:30:00Z"

Write-Host "Processing real store footage..."

$cameras = @(
    @{ File="CAM 3.mp4"; ID="CAM_3" },
    @{ File="CAM 1.mp4"; ID="CAM_1" },
    @{ File="CAM 2.mp4"; ID="CAM_2" },
    @{ File="CAM 5.mp4"; ID="CAM_5" }
)

foreach ($cam in $cameras) {
    Write-Host "Starting processing for $($cam.File) ($($cam.ID))..."
    .\venv\Scripts\python.exe -m pipeline.detect --video "$clips_dir\$($cam.File)" --camera-id $($cam.ID) --layout $layout --start-utc $start_utc --post-live
}

Write-Host "Done. Check data\events_output.jsonl"
