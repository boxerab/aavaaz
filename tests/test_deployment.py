"""
Tests for deployment targets (Test Matrix §18).

Validates Docker builds, Helm charts, Modal configs, and Lambda handler.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
CHART_DIR = PROJECT_ROOT / "deploy" / "helm" / "aavaaz"
CPU_DOCKERFILES = ["Dockerfile.cpu", "Dockerfile.edge", "Dockerfile.jetson"]


CPU_TORCH_INDEX = "--extra-index-url https://download.pytorch.org/whl/cpu "


def pip_install_lines(dockerfile_name):
    content = (PROJECT_ROOT / dockerfile_name).read_text()
    return [
        line.strip().replace(CPU_TORCH_INDEX, "").removesuffix(" && \\")
        for line in content.splitlines()
        if "pip install" in line and ("WHISPER_LIVE_SOURCE" in line or "[whisper" in line)
    ]


def helm_template(*extra_args):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm not installed")
    return subprocess.run(
        [helm, "template", "aavaaz", str(CHART_DIR), *extra_args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


class TestDockerfiles:
    """18.1-18.2 - Dockerfile validation."""

    def test_dockerfile_exists(self):
        """Main Dockerfile should exist."""
        assert (PROJECT_ROOT / "Dockerfile").exists()

    def test_dockerfile_lambda_exists(self):
        """Lambda Dockerfile should exist."""
        assert (PROJECT_ROOT / "Dockerfile.lambda").exists()

    def test_dockerfile_has_valid_base_image(self):
        """Dockerfile should have a FROM instruction."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "FROM" in content

    def test_dockerfile_lambda_has_valid_base(self):
        """Lambda Dockerfile should use AWS Lambda base or compatible."""
        content = (PROJECT_ROOT / "Dockerfile.lambda").read_text()
        assert "FROM" in content

    def test_dockerfile_installs_requirements(self):
        """Dockerfile should install Python dependencies."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "pip" in content or "uv" in content or "requirements" in content

    def test_dockerfile_copies_source(self):
        """Dockerfile should copy application source."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "COPY" in content


class TestCpuDockerfiles:
    """CPU, edge and Jetson images share one install recipe."""

    @pytest.mark.parametrize("name", CPU_DOCKERFILES)
    def test_exists(self, name):
        assert (PROJECT_ROOT / name).exists()

    @pytest.mark.parametrize("name", CPU_DOCKERFILES[1:])
    def test_install_lines_match_cpu(self, name):
        assert pip_install_lines(name) == pip_install_lines("Dockerfile.cpu")

    def test_cpu_installs_torch_from_cpu_index(self):
        content = (PROJECT_ROOT / "Dockerfile.cpu").read_text()
        assert "https://download.pytorch.org/whl/cpu" in content

    def test_default_models(self):
        assert '"tiny"' in (PROJECT_ROOT / "Dockerfile.edge").read_text()
        assert '"small"' in (PROJECT_ROOT / "Dockerfile.cpu").read_text()
        assert '"small"' in (PROJECT_ROOT / "Dockerfile.jetson").read_text()


class TestImagesWorkflow:
    """Release workflow builds the GPU and CPU images."""

    def test_references_both_dockerfiles(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "images.yml").read_text()
        assert "dockerfile: Dockerfile\n" in content
        assert "dockerfile: Dockerfile.cpu" in content
        assert "aavaaz-gpu" in content
        assert "aavaaz-cpu" in content


class TestHelmChart:
    """18.5 - Helm chart structure validation."""

    def test_helm_chart_yaml_exists(self):
        """Chart.yaml should exist."""
        chart_path = PROJECT_ROOT / "deploy" / "helm" / "aavaaz" / "Chart.yaml"
        assert chart_path.exists()

    def test_helm_values_exists(self):
        """values.yaml should exist."""
        values_path = PROJECT_ROOT / "deploy" / "helm" / "aavaaz" / "values.yaml"
        assert values_path.exists()
        assert len(values_path.read_text()) > 0

    def test_helm_templates_directory(self):
        """templates/ directory should exist and be non-empty."""
        templates = PROJECT_ROOT / "deploy" / "helm" / "aavaaz" / "templates"
        assert templates.is_dir()
        assert len(list(templates.iterdir())) > 0

    def test_gpu_enabled_requests_a_gpu(self):
        assert "nvidia.com/gpu" in helm_template()

    def test_gpu_disabled_omits_gpu_limit(self):
        rendered = helm_template("--set", "gpu.enabled=false")
        assert "nvidia.com/gpu" not in rendered
        assert "faster_whisper" in rendered


class TestModalConfigs:
    """18.3-18.4 - Modal deployment files."""

    def test_modal_app_exists(self):
        """Batch Modal app should exist."""
        assert (PROJECT_ROOT / "deploy" / "modal" / "app.py").exists()

    def test_modal_app_live_exists(self):
        """Live Modal app should exist."""
        assert (PROJECT_ROOT / "deploy" / "modal" / "app_live.py").exists()

    def test_modal_app_has_app_definition(self):
        """Modal app should define modal.App."""
        content = (PROJECT_ROOT / "deploy" / "modal" / "app.py").read_text()
        assert "modal.App" in content

    def test_modal_app_live_has_websocket(self):
        """Live app should have WebSocket endpoint."""
        content = (PROJECT_ROOT / "deploy" / "modal" / "app_live.py").read_text()
        assert "websocket" in content.lower()
        assert "/ws" in content

    def test_modal_app_live_has_health(self):
        """Live app should have health endpoint."""
        content = (PROJECT_ROOT / "deploy" / "modal" / "app_live.py").read_text()
        assert "/health" in content

    def test_modal_app_live_has_gpu(self):
        """Live app should request a GPU."""
        content = (PROJECT_ROOT / "deploy" / "modal" / "app_live.py").read_text()
        assert "gpu" in content.lower()


class TestTerraformConfigs:
    """18.6-18.7 - Terraform configuration validation."""

    def test_terraform_ecs_exists(self):
        """ECS Terraform config should exist."""
        tf_dir = PROJECT_ROOT / "deploy" / "terraform"
        assert tf_dir.exists()
        tf_files = list(tf_dir.glob("*.tf"))
        assert len(tf_files) > 0

    def test_terraform_lambda_exists(self):
        """Lambda Terraform config should exist."""
        tf_dir = PROJECT_ROOT / "deploy" / "terraform-lambda"
        assert tf_dir.exists()
        tf_files = list(tf_dir.glob("*.tf"))
        assert len(tf_files) > 0

    def test_terraform_has_provider(self):
        """Terraform should define a provider."""
        tf_dir = PROJECT_ROOT / "deploy" / "terraform"
        all_content = ""
        for tf_file in tf_dir.glob("*.tf"):
            all_content += tf_file.read_text()
        assert "provider" in all_content


class TestLambdaHandler:
    """18.8-18.9 - Lambda handler logic."""

    def test_lambda_handler_module_importable(self):
        """Lambda handler should be importable."""
        # Need to mock heavy deps
        sys.modules.setdefault("whisper_live", MagicMock())
        sys.modules.setdefault("whisper_live.server", MagicMock())
        sys.modules.setdefault("faster_whisper", MagicMock())
        sys.modules.setdefault("torch", MagicMock())

        from aavaaz.serverless import lambda_handler

        assert hasattr(lambda_handler, "handler") or hasattr(lambda_handler, "lambda_handler")

    def test_lambda_env_vars_documented(self):
        """Lambda handler should document expected env vars."""
        handler_path = PROJECT_ROOT / "aavaaz" / "serverless" / "lambda_handler.py"
        assert handler_path.exists()
        # Should reference AAVAAZ_MODEL at minimum
        assert "AAVAAZ_MODEL" in handler_path.read_text()


class TestHealthEndpointConsistency:
    """18.10 - Health endpoint on all deployments."""

    def test_modal_live_has_health(self):
        content = (PROJECT_ROOT / "deploy" / "modal" / "app_live.py").read_text()
        assert '"/health"' in content

    def test_modal_batch_has_health(self):
        content = (PROJECT_ROOT / "deploy" / "modal" / "app.py").read_text()
        # Batch app might have health check too
        assert "/health" in content or "health" in content.lower()
