"""Tests for common_objects module."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from common_objects import (
    Direction,
    BoardRecord,
    validate_contract,
    dealNo2dealer,
    dealNo2vul,
    str_to_side,
)


class TestDirection:
    """Tests for Direction enum."""
    
    def test_from_str(self):
        """Test Direction.from_str() method."""
        assert Direction.from_str("N") == Direction.NORTH
        assert Direction.from_str("E") == Direction.EAST
        assert Direction.from_str("S") == Direction.SOUTH
        assert Direction.from_str("W") == Direction.WEST
    
    def test_next(self):
        """Test Direction.next() method."""
        assert Direction.NORTH.next() == Direction.EAST
        assert Direction.EAST.next() == Direction.SOUTH
        assert Direction.SOUTH.next() == Direction.WEST
        assert Direction.WEST.next() == Direction.NORTH
    
    def test_partner(self):
        """Test Direction.partner() method."""
        assert Direction.NORTH.partner() == Direction.SOUTH
        assert Direction.EAST.partner() == Direction.WEST
        assert Direction.SOUTH.partner() == Direction.NORTH
        assert Direction.WEST.partner() == Direction.EAST
    
    def test_previous(self):
        """Test Direction.previous() method."""
        assert Direction.NORTH.previous() == Direction.WEST
        assert Direction.EAST.previous() == Direction.NORTH
        assert Direction.SOUTH.previous() == Direction.EAST
        assert Direction.WEST.previous() == Direction.SOUTH
    
    def test_abbreviation(self):
        """Test Direction.abbreviation() method."""
        assert Direction.NORTH.abbreviation() == "N"
        assert Direction.EAST.abbreviation() == "E"
        assert Direction.SOUTH.abbreviation() == "S"
        assert Direction.WEST.abbreviation() == "W"


class TestContractValidation:
    """Tests for contract validation."""
    
    def test_valid_contracts(self):
        """Test validation of valid contracts."""
        assert validate_contract("1C") == "1C"
        assert validate_contract("3NT") == "3N"
        assert validate_contract("7S") == "7S"
        assert validate_contract("4HX") == "4HX"
        assert validate_contract("2DXX") == "2DXX"
        assert validate_contract("PASS") == "AP"
    
    def test_invalid_contracts(self):
        """Test validation of invalid contracts."""
        assert validate_contract("8S") == ""  # Invalid level
        assert validate_contract("1T") == ""  # Invalid strain
        assert validate_contract("") == ""
        assert validate_contract(None) == ""


class TestDealNumberFunctions:
    """Tests for deal number utility functions."""
    
    def test_dealNo2dealer(self):
        """Test deal number to dealer conversion."""
        assert dealNo2dealer(1) == "N"
        assert dealNo2dealer(2) == "E"
        assert dealNo2dealer(3) == "S"
        assert dealNo2dealer(4) == "W"
        assert dealNo2dealer(5) == "N"
    
    def test_dealNo2vul(self):
        """Test deal number to vulnerability conversion."""
        assert dealNo2vul(1) == "Z"  # None
        assert dealNo2vul(2) == "N"  # NS
        assert dealNo2vul(3) == "E"  # EW
        assert dealNo2vul(16) == "E"  # Wraps around


class TestSideConversion:
    """Tests for side conversion functions."""
    
    def test_str_to_side(self):
        """Test string to side conversion."""
        assert str_to_side("N") == "NS"
        assert str_to_side("S") == "NS"
        assert str_to_side("E") == "EW"
        assert str_to_side("W") == "EW"
        assert str_to_side("X") == ""
        assert str_to_side("") == ""


class TestBoardRecord:
    """Tests for BoardRecord dataclass."""
    
    def test_default_values(self):
        """Test BoardRecord default values."""
        record = BoardRecord()
        assert record.EventName == "UNKNOWN"
        assert record.MatchName == "UNKNOWN"
        assert record.DealNum == 0
        assert record.Dealer == ""
        assert record.Vulnerability == "X"
    
    def test_custom_values(self):
        """Test BoardRecord with custom values."""
        record = BoardRecord(
            EventName="Test Event",
            DealNum=5,
            Dealer="N",
            Vulnerability="Z",
            Contract="4S"
        )
        assert record.EventName == "Test Event"
        assert record.DealNum == 5
        assert record.Dealer == "N"
        assert record.Vulnerability == "Z"
        assert record.Contract == "4S"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



