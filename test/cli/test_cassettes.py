import pytest
import yaml
from _pytest.main import ExitCode


@pytest.mark.endpoints("success", "upload_file")
def test_store_cassette(cli, schema_url, tmp_path):
    file_ = tmp_path / "output.yaml"
    result = cli.run(schema_url, f"--store-network-log={file_}", "--hypothesis-max-examples=2")
    assert result.exit_code == ExitCode.OK
    with file_.open() as fd:
        cassette = yaml.safe_load(fd)
    assert len(cassette["interactions"]) == 3
    assert cassette["interactions"][0]["id"] == "0"
    assert cassette["interactions"][0]["status"] == "SUCCESS"
