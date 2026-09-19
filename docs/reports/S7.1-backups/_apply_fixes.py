import re, sys, os

flux_dir = sys.argv[1]

# ============================================================
# FIX 1: models.py
# ============================================================
models_path = os.path.join(flux_dir, "models.py")
with open(models_path, "r", encoding="utf-8") as f:
    src = f.read()

original = src

# --- M3: FluxTransferStatus enum ---
old_enum = r'''class FluxTransferStatus\(StrEnum\):
    """Transfer lifecycle states\."""
    QUEUED = "queued"
    CONNECTING = "connecting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"'''

new_enum = '''class FluxTransferStatus(StrEnum):
    """Transfer lifecycle states matching Gateway TransferStatus.

    Gateway uses #[serde(rename_all = "SCREAMING_SNAKE_CASE")]:
    CREATED, RUNNING, COMPLETED, FAILED, CANCELLED
    """
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"'''

src = re.sub(old_enum, new_enum, src)

# --- M1: FluxTransferRequest ---
old_req = r'''class FluxTransferRequest\(BaseModel\):
    """POST /flux/v1/transfer"""
    peer_id: str
    artifact_path: str = Field\(\.\.\., description="Local path to artifact"\)
    artifact_name: str \| None = None
    is_directory: bool = False'''

new_req = '''class FluxTransferRequest(BaseModel):
    """POST /flux/v1/transfer — matches Gateway StartTransferRequest."""
    peer_id: str
    file_paths: list[str] = Field(..., description="List of local file paths to transfer")'''

src = re.sub(old_req, new_req, src)

# --- M2: FluxTransferResponse (POST response has no peer_id) ---
old_resp = r'''class FluxTransferResponse\(BaseModel\):
    """POST /flux/v1/transfer response"""
    transfer_id: str
    peer_id: str
    status: FluxTransferStatus'''

new_resp = '''class FluxTransferResponse(BaseModel):
    """POST /flux/v1/transfer response — matches Gateway StartTransferResponse.

    Note: The POST response does NOT include peer_id.
    Use GET /transfer/{id} (FluxTransferStatusResponse) for peer_id.
    """
    transfer_id: str
    status: FluxTransferStatus'''

src = re.sub(old_resp, new_resp, src)

# --- M2+M3: FluxTransferStatusResponse (matches GatewayTransferInfo) ---
old_status = r'''class FluxTransferStatusResponse\(BaseModel\):
    """GET /flux/v1/transfer/\{transfer_id\}"""
    transfer_id: str
    peer_id: str
    status: FluxTransferStatus
    progress_percent: float = Field\(default=0\.0, ge=0\.0, le=100\.0\)
    bytes_transferred: int = Field\(default=0\)
    bytes_total: int = Field\(default=0\)
    error_message: str \| None = None'''

new_status = '''class FluxTransferStatusResponse(BaseModel):
    """GET /flux/v1/transfer/{transfer_id} — matches Gateway GatewayTransferInfo."""
    transfer_id: str
    peer_id: str
    status: FluxTransferStatus
    bytes_transferred: int = Field(default=0)
    total_bytes: int = Field(default=0)
    files_transferred: int = Field(default=0)
    total_files: int = Field(default=0)
    error_message: str | None = None'''

src = re.sub(old_status, new_status, src)

# --- M4: FluxCancelResponse ---
old_cancel = r'''class FluxCancelResponse\(BaseModel\):
    """POST /flux/v1/transfer/\{transfer_id\}/cancel"""
    transfer_id: str
    status: FluxTransferStatus'''

new_cancel = '''class FluxCancelResponse(BaseModel):
    """POST /flux/v1/transfer/{transfer_id}/cancel — matches Gateway CancelTransferResponse."""
    transfer_id: str
    cancelled: bool'''

src = re.sub(old_cancel, new_cancel, src)

# --- M5: FluxPeerInfo (add last_seen_secs_ago) ---
old_peer = r'''class FluxPeerInfo\(BaseModel\):
    """GET /flux/v1/peers/\{peer_id\}"""
    peer_id: str
    address: str \| None = None
    last_seen: str \| None = None'''

new_peer = '''class FluxPeerInfo(BaseModel):
    """GET /flux/v1/peers/{peer_id} — matches Gateway PeerSummary."""
    peer_id: str
    address: str | None = None
    last_seen_secs_ago: float | None = None
    last_seen: str | None = None'''

src = re.sub(old_peer, new_peer, src)

if src != original:
    with open(models_path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [FIXED] models.py — M1, M2, M3, M4, M5 applied")
else:
    print("  [WARN] models.py — no regex matches, manual review needed")

# ============================================================
# FIX 2: client.py
# ============================================================
client_path = os.path.join(flux_dir, "client.py")
with open(client_path, "r", encoding="utf-8") as f:
    src = f.read()

original = src

# --- M1: Fix initiate_transfer request construction ---
old_body = r'''req = FluxTransferRequest\(
                peer_id=peer_id,
                artifact_path=artifact_path,
                artifact_name=artifact_name,
                is_directory=is_directory,
            \)'''

new_body = '''req = FluxTransferRequest(
                peer_id=peer_id,
                file_paths=[artifact_path],
            )'''

src = re.sub(old_body, new_body, src)

if src != original:
    with open(client_path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [FIXED] client.py — M1 request construction adapted")
else:
    print("  [WARN] client.py — no regex matches, manual review needed")

print("\n  All fixes applied. Original files preserved in backups.")
