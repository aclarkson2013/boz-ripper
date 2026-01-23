"""GPU detection for transcoding capabilities."""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """Information about a detected GPU."""

    name: str
    vendor: str  # nvidia, intel, amd
    nvenc: bool = False
    nvenc_generation: int = 0
    qsv: bool = False
    hevc: bool = False
    av1: bool = False


def detect_nvidia_gpu() -> Optional[GPUInfo]:
    """Detect NVIDIA GPU and its capabilities.

    Returns:
        GPUInfo if NVIDIA GPU found, None otherwise
    """
    try:
        # Try nvidia-smi to get GPU info
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        gpu_name = result.stdout.strip()
        if not gpu_name:
            return None

        logger.info(f"Detected NVIDIA GPU: {gpu_name}")

        # Determine NVENC generation and capabilities based on GPU name
        nvenc_gen = 0
        hevc = False
        av1 = False

        gpu_lower = gpu_name.lower()

        # RTX 40 series (Ada Lovelace) - NVENC 9th gen
        if any(x in gpu_lower for x in ["rtx 40", "rtx40", "4090", "4080", "4070", "4060"]):
            nvenc_gen = 9
            hevc = True
            av1 = True  # RTX 40 series supports AV1 encoding

        # RTX 30 series (Ampere) - NVENC 8th gen
        elif any(x in gpu_lower for x in ["rtx 30", "rtx30", "3090", "3080", "3070", "3060"]):
            nvenc_gen = 8
            hevc = True
            av1 = False

        # RTX 20 series (Turing) - NVENC 7th gen
        elif any(x in gpu_lower for x in ["rtx 20", "rtx20", "2080", "2070", "2060"]):
            nvenc_gen = 7
            hevc = True
            av1 = False

        # GTX 16 series (Turing) - NVENC 7th gen
        elif any(x in gpu_lower for x in ["gtx 16", "1660", "1650"]):
            nvenc_gen = 7
            hevc = True
            av1 = False

        # GTX 10 series (Pascal) - NVENC 6th gen
        elif any(x in gpu_lower for x in ["gtx 10", "1080", "1070", "1060", "1050"]):
            nvenc_gen = 6
            hevc = True
            av1 = False

        # Older GPUs
        elif "gtx" in gpu_lower or "nvidia" in gpu_lower:
            nvenc_gen = 5
            hevc = False
            av1 = False

        return GPUInfo(
            name=gpu_name,
            vendor="nvidia",
            nvenc=nvenc_gen > 0,
            nvenc_generation=nvenc_gen,
            qsv=False,
            hevc=hevc,
            av1=av1,
        )

    except FileNotFoundError:
        logger.debug("nvidia-smi not found")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi timed out")
        return None
    except Exception as e:
        logger.warning(f"NVIDIA detection failed: {e}")
        return None


def detect_intel_gpu() -> Optional[GPUInfo]:
    """Detect Intel GPU with QuickSync support.

    Returns:
        GPUInfo if Intel GPU with QSV found, None otherwise
    """
    try:
        # On Windows, check for Intel GPU via WMI
        import wmi

        c = wmi.WMI()
        for gpu in c.Win32_VideoController():
            if "intel" in gpu.Name.lower():
                gpu_name = gpu.Name

                # Check for QuickSync support (6th gen+ Intel Core)
                qsv = False
                hevc = False

                # Modern Intel GPUs with good QSV
                if any(x in gpu_name.lower() for x in ["uhd", "iris", "arc"]):
                    qsv = True
                    hevc = True

                if qsv:
                    logger.info(f"Detected Intel GPU with QuickSync: {gpu_name}")
                    return GPUInfo(
                        name=gpu_name,
                        vendor="intel",
                        nvenc=False,
                        nvenc_generation=0,
                        qsv=True,
                        hevc=hevc,
                        av1=False,
                    )

        return None

    except ImportError:
        logger.debug("WMI not available for Intel detection")
        return None
    except Exception as e:
        logger.warning(f"Intel detection failed: {e}")
        return None


def detect_gpu() -> Optional[GPUInfo]:
    """Detect the best available GPU for transcoding.

    Prioritizes NVIDIA over Intel.

    Returns:
        GPUInfo for best GPU, or None if no suitable GPU found
    """
    # Try NVIDIA first (preferred for transcoding)
    nvidia = detect_nvidia_gpu()
    if nvidia:
        return nvidia

    # Try Intel QuickSync
    intel = detect_intel_gpu()
    if intel:
        return intel

    logger.info("No hardware encoder detected, will use CPU")
    return None


def get_handbrake_encoder(gpu: Optional[GPUInfo], codec: str = "h264") -> str:
    """Get the HandBrake encoder name for the given GPU.

    Args:
        gpu: GPU info or None for CPU
        codec: Target codec (h264, h265/hevc, av1)

    Returns:
        HandBrake encoder name
    """
    codec = codec.lower()

    if gpu is None:
        # CPU encoders
        if codec in ("h265", "hevc"):
            return "x265"
        elif codec == "av1":
            return "svt_av1"
        else:
            return "x264"

    if gpu.vendor == "nvidia" and gpu.nvenc:
        if codec in ("h265", "hevc") and gpu.hevc:
            return "nvenc_h265"
        elif codec == "av1" and gpu.av1:
            return "nvenc_av1"
        else:
            return "nvenc_h264"

    if gpu.vendor == "intel" and gpu.qsv:
        if codec in ("h265", "hevc") and gpu.hevc:
            return "qsv_h265"
        else:
            return "qsv_h264"

    # Fallback to CPU
    if codec in ("h265", "hevc"):
        return "x265"
    return "x264"
