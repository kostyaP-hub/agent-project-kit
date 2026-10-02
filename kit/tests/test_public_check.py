import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/public-check.py'
spec = importlib.util.spec_from_file_location('public_check', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_private_data_report_does_not_echo_values(tmp_path):
    path = tmp_path / 'note.md'
    private = 'PrivateCustomer'
    path.write_text('Reach someone' + '@private-domain.invalid\n' + private + '\n')
    result = module.findings(path, tmp_path, [private])
    assert len(result) == 2
    assert private not in str(result)

def test_doc_addresses_and_examples_allowed(tmp_path):
    path = tmp_path / 'note.md'
    path.write_text('test@example.com 127.0.0.1 192.0.2.5\n')
    assert module.findings(path, tmp_path, []) == []

def test_binary_and_symlinks_rejected(tmp_path):
    path = tmp_path / 'note.md'
    path.write_bytes(b'\xff\xff')
    assert module.findings(path, tmp_path, [])[0][1] == 'unreadable-or-binary'
    link = tmp_path / 'link.md'
    link.symlink_to(path)
    assert module.findings(link, tmp_path, [])[0][1] == 'symlink'
