"""Test the pinned Streamlit wire-cache mitigation, without models or HTTP calls."""
from pathlib import Path
import re
from unittest.mock import patch
from streamlit import config
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.runtime.forward_msg_cache import populate_hash_if_needed


def startup_threshold():
    script=(Path(__file__).resolve().parents[1]/'startup.sh').read_text()
    return int(re.search(r'--global\.minCachedMessageSize (\d+)',script).group(1))


def message():
    msg=ForwardMsg()
    msg.delta.new_element.markdown.body='Large repeated official evidence. '*1000
    return msg


def test_repeated_evidence_is_sent_in_full_instead_of_cache_reference():
    normal=message();populate_hash_if_needed(normal)
    assert normal.metadata.cacheable  # Reproduces the affected >10KB path.
    option=config.get_option
    with patch('streamlit.runtime.forward_msg_cache.config.get_option',side_effect=lambda key:startup_threshold() if key=='global.minCachedMessageSize' else option(key)):
        for _ in range(4):
            full=message();populate_hash_if_needed(full)
            assert full.hash and not full.metadata.cacheable
            assert full.WhichOneof('type')=='delta'
            assert full.delta.new_element.markdown.body==normal.delta.new_element.markdown.body


def test_threshold_exceeds_all_allowed_wire_messages_and_keeps_persistence():
    assert startup_threshold()>config.get_option('server.maxMessageSize')*1024*1024
    script=(Path(__file__).resolve().parents[1]/'startup.sh').read_text()
    assert 'GRANTSCOPE_DATA_DIR' in script and '/home/grantscope' in script
    assert 'enableCORS false' not in script and 'enableXsrfProtection false' not in script
