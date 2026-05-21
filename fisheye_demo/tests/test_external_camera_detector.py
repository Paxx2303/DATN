"""
Property-based tests for external_camera_detector.py
Tests correctness properties for camera discovery and serialization.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

# Add parent directory to path to import fisheye_demo modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from external_camera_detector import (
    ExternalCameraItem,
    StreamType,
    serialize_camera_item,
    deserialize_camera_item,
)


# Strategy for generating valid ExternalCameraItem objects
@st.composite
def external_camera_items(draw):
    """Generate arbitrary ExternalCameraItem objects for property testing."""
    return ExternalCameraItem(
        index=draw(st.integers(min_value=0, max_value=100)),
        embed_url=draw(st.text(min_size=1, max_size=200)),
        youtube_id=draw(st.text(min_size=6, max_size=20, alphabet=st.characters(blacklist_characters='"\''))),
        title=draw(st.text(min_size=1, max_size=120)),
        snapshot_url=draw(st.text(min_size=1, max_size=200)),
        stream_type=draw(st.sampled_from(list(StreamType))),
        priority=draw(st.integers(min_value=1, max_value=4)),
        coordinates=draw(
            st.one_of(
                st.none(),
                st.tuples(
                    st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
                    st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
                ),
            )
        ),
    )


class TestCameraDiscoveryRoundTripConsistency:
    """Property 1: Camera Discovery Round-Trip Consistency
    
    Validates: Requirements 11.4
    
    Property: deserialize_camera_item(serialize_camera_item(item)) == item
    """

    @given(external_camera_items())
    def test_round_trip_consistency(self, item):
        """Test that serialization and deserialization preserve all data."""
        serialized = serialize_camera_item(item)
        deserialized = deserialize_camera_item(serialized)
        
        assert deserialized == item, (
            f"Round-trip failed:\n"
            f"Original: {item}\n"
            f"Deserialized: {deserialized}"
        )

    @given(external_camera_items())
    def test_serialized_is_json_compatible(self, item):
        """Test that serialized form is JSON-compatible (no enums)."""
        serialized = serialize_camera_item(item)
        
        # Check that stream_type is a string, not an enum
        assert isinstance(serialized['stream_type'], str), (
            f"stream_type should be string, got {type(serialized['stream_type'])}"
        )
        
        # Verify it's a valid StreamType value
        assert serialized['stream_type'] in [st.value for st in StreamType], (
            f"Invalid stream_type value: {serialized['stream_type']}"
        )

    def test_deserialize_missing_required_field(self):
        """Test that deserialize raises ValueError for missing required fields."""
        incomplete_data = {
            'index': 0,
            'embed_url': 'http://example.com',
            'youtube_id': 'abc123',
            # Missing 'title' and 'snapshot_url'
        }
        
        with pytest.raises(ValueError, match="Missing required fields"):
            deserialize_camera_item(incomplete_data)

    def test_deserialize_invalid_stream_type(self):
        """Test that deserialize raises ValueError for invalid stream_type."""
        invalid_data = {
            'index': 0,
            'embed_url': 'http://example.com',
            'youtube_id': 'abc123',
            'title': 'Test Camera',
            'snapshot_url': 'http://example.com/snap.jpg',
            'stream_type': 'invalid_type',
        }
        
        with pytest.raises(ValueError, match="Invalid stream_type"):
            deserialize_camera_item(invalid_data)

    def test_deserialize_with_defaults(self):
        """Test that deserialize applies correct defaults for optional fields."""
        minimal_data = {
            'index': 0,
            'embed_url': 'http://example.com',
            'youtube_id': 'abc123',
            'title': 'Test Camera',
            'snapshot_url': 'http://example.com/snap.jpg',
        }
        
        item = deserialize_camera_item(minimal_data)
        
        assert item.stream_type == StreamType.YOUTUBE_LIVE
        assert item.priority == 1
        assert item.coordinates is None


class TestExternalCameraItemDataclass:
    """Unit tests for ExternalCameraItem dataclass."""

    def test_create_with_all_fields(self):
        """Test creating ExternalCameraItem with all fields."""
        item = ExternalCameraItem(
            index=0,
            embed_url='http://example.com/embed',
            youtube_id='abc123def456',
            title='Camera 1',
            snapshot_url='http://example.com/snap.jpg',
            stream_type=StreamType.YOUTUBE_LIVE,
            priority=2,
            coordinates=(10.5, 20.5),
        )
        
        assert item.index == 0
        assert item.title == 'Camera 1'
        assert item.priority == 2
        assert item.coordinates == (10.5, 20.5)

    def test_create_with_defaults(self):
        """Test creating ExternalCameraItem with default values."""
        item = ExternalCameraItem(
            index=0,
            embed_url='http://example.com/embed',
            youtube_id='abc123def456',
            title='Camera 1',
            snapshot_url='http://example.com/snap.jpg',
        )
        
        assert item.stream_type == StreamType.YOUTUBE_LIVE
        assert item.priority == 1
        assert item.coordinates is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
