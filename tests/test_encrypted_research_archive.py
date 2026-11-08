"""Synthetic cache privacy, authentication and loss/restoration checks."""
import base64
import os
import shutil
from pathlib import Path
import pytest
from services.research_engine import ResearchStore
from services.research_archive import EncryptedResearchArchive

SCOPE='a'*64
OTHER='b'*64
KEY=base64.urlsafe_b64encode(bytes(range(32))).decode()

def configured(tmp_path,monkeypatch):
    private=tmp_path/'private';archive=tmp_path/'smb'
    archive.mkdir();archive.chmod(0o777)
    monkeypatch.setenv('GRANTSCOPE_RESEARCH_CACHE',str(private))
    monkeypatch.setenv('GRANTSCOPE_RESEARCH_ARCHIVE_DIR',str(archive))
    monkeypatch.setenv('GRANTSCOPE_RESEARCH_ARCHIVE_KEY',KEY)
    return ResearchStore(),private,archive


def test_0700_plaintext_store_and_ciphertext_only_on_0777_archive(tmp_path,monkeypatch):
    store,private,archive=configured(tmp_path,monkeypatch)
    records={'1':{'state':'RESEARCHED_AND_VALIDATED','notes':'PRIVATE PROJECT UNIQUE MARKER'}}
    store.save(SCOPE,records)
    assert private.stat().st_mode & 0o777==0o700
    assert (private/(SCOPE+'.json')).stat().st_mode & 0o777==0o600
    blobs=list(archive.iterdir());assert len(blobs)==1 and blobs[0].suffix=='.aesgcm'
    assert b'PRIVATE PROJECT UNIQUE MARKER' not in blobs[0].read_bytes()
    # Remove only this synthetic fixture's ephemeral directory, modeling loss of a container.
    shutil.rmtree(private)
    assert store.load(SCOPE)==records
    assert private.stat().st_mode & 0o777==0o700


def test_wrong_key_tamper_and_scope_swap_fail_closed_without_plaintext(tmp_path,monkeypatch):
    store,private,archive=configured(tmp_path,monkeypatch);store.save(SCOPE,{'1':{'state':'synthetic'}})
    original=(archive/(SCOPE+'.aesgcm')).read_bytes();shutil.rmtree(private)
    wrong=EncryptedResearchArchive(archive,base64.urlsafe_b64encode(b'x'*32).decode())
    with pytest.raises(ValueError,match='authentication'):wrong.load(SCOPE)
    assert not private.exists()
    (archive/(OTHER+'.aesgcm')).write_bytes(original)
    with pytest.raises(ValueError,match='authentication'):store.load(OTHER)
    (archive/(SCOPE+'.aesgcm')).write_bytes(original[:-1]+bytes([original[-1]^1]))
    with pytest.raises(ValueError,match='authentication'):store.load(SCOPE)
    assert not private.exists()


def test_primary_0777_and_symlinks_still_rejected_even_with_encryption(tmp_path,monkeypatch):
    store,private,archive=configured(tmp_path,monkeypatch)
    private.mkdir(mode=0o777);private.chmod(0o777)
    with pytest.raises(ValueError,match='must be private'):store.save(SCOPE,{})
    assert not list(archive.iterdir())
    private.rmdir();target=tmp_path/'target';target.mkdir(mode=0o700);private.symlink_to(target)
    with pytest.raises(ValueError,match='must be private'):store.save(SCOPE,{})


def test_missing_key_and_backup_failure_do_not_acknowledge_unbacked_save(tmp_path,monkeypatch):
    store,private,archive=configured(tmp_path,monkeypatch)
    monkeypatch.delenv('GRANTSCOPE_RESEARCH_ARCHIVE_KEY')
    with pytest.raises(ValueError,match='key'):ResearchStore()
    store.archive.save=lambda *args:(_ for _ in ()).throw(OSError('Synthetic backup failure'))
    with pytest.raises(OSError):store.save(SCOPE,{'1':{'state':'synthetic'}})
    assert not (private/(SCOPE+'.json')).exists()


def test_versions_and_legacy_data_preserved(tmp_path,monkeypatch):
    store,private,archive=configured(tmp_path,monkeypatch)
    legacy=tmp_path/'legacy';legacy.mkdir();legacy_file=legacy/'existing.json';legacy_file.write_text('UNTOUCHED')
    old={'1':{'input_key':'old','protocol_hash':'v1','state':'old'}}
    store.save(SCOPE,old)
    store.save(SCOPE,{'1':{'input_key':'new','protocol_hash':'v2','state':'new'}})
    recovered=store.load(SCOPE)
    assert recovered['1']['prior_versions'][0]==old['1']
    assert legacy_file.read_text()=='UNTOUCHED'
    assert set(recovered)=={'1'}


def test_generic_engine_reuses_authenticated_restore_without_repeat_calls(tmp_path,monkeypatch):
    from tests.test_integration_search import screen
    from tests.test_dynamic_research import Provider,Evidence
    from services.integration_search import research_one_candidate
    store,private,archive=configured(tmp_path,monkeypatch)
    screening=screen();provider=Provider()
    first=research_one_candidate(screening,'910001',provider,cache=store,evidence_client=Evidence())
    assert first['records']['910001']['state']=='RESEARCHED_AND_VALIDATED' and len(provider.calls)==2
    # New empty active path models a replaced container, without deleting even fixture data.
    replacement=tmp_path/'replacement'
    monkeypatch.setenv('GRANTSCOPE_RESEARCH_CACHE',str(replacement))
    restored=ResearchStore();provider2=Provider()
    second=research_one_candidate(screening,'910001',provider2,cache=restored,evidence_client=Evidence())
    assert not provider2.calls and second['records']['910001']['cache_reused']
    assert replacement.stat().st_mode & 0o777==0o700
    assert private.exists() and list(archive.glob('*.aesgcm'))
