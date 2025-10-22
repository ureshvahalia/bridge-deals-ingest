"""Tests for auction processing module."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from auction import process_auction
from common_objects import Direction


class TestAuctionProcessing:
    """Tests for process_auction function."""
    
    def test_all_pass(self):
        """Test all-pass auction."""
        result = process_auction(Direction.NORTH, "P-P-P-P")
        assert result["DerivedContract"] == "AP"
        assert result["Opener"] == ""
        assert result["Opening"] == ""
        assert result["AuctionCheck"] == "Legal"
    
    def test_simple_auction(self):
        """Test simple 1C-P-1H-P-1N auction."""
        result = process_auction(Direction.NORTH, "1C-P-1H-P-1N-P-P-P")
        assert result["DerivedContract"] == "1N"
        assert result["Opener"] == "N"
        assert result["Opening"] == "1C"
        assert result["DerivedDeclarer"] == "N"
        assert result["AuctionCheck"] == "Legal"
    
    def test_doubled_contract(self):
        """Test doubled contract."""
        result = process_auction(Direction.NORTH, "1S-P-P-X-P-P-P")
        assert result["DerivedContract"] == "1SX"
        assert result["Opener"] == "N"
        # Note: process_auction doesn't return "Premium" separately
        assert result["AuctionCheck"] == "Legal"
    
    def test_redoubled_contract(self):
        """Test redoubled contract."""
        result = process_auction(Direction.NORTH, "1D-X-XX-P-P-P")
        assert result["DerivedContract"] == "1DXX"
        # Note: process_auction doesn't return "Premium" separately
        assert result["AuctionCheck"] == "Legal"
    
    def test_intervention(self):
        """Test auction with intervention."""
        result = process_auction(Direction.NORTH, "1C-1S-P-P-P")
        assert result["Opening"] == "1C"
        assert result["Intervention"] == "1S"
        assert result["Intervener"] == "E"
        assert result["AuctionCheck"] == "Legal"
    
    def test_illegal_double(self):
        """Test illegal double (doubling own side)."""
        result = process_auction(Direction.NORTH, "1C-P-X-P-P-P")
        assert result["AuctionCheck"] == "Illegal"
    
    def test_illegal_bid_sequence(self):
        """Test illegal bid sequence (1C-1C)."""
        result = process_auction(Direction.NORTH, "1C-1C")
        assert result["AuctionCheck"] == "Illegal"
    
    def test_slam_auction(self):
        """Test slam-level auction."""
        result = process_auction(Direction.NORTH, "1C-P-1H-P-6N-P-P-P")
        assert result["DerivedContract"] == "6N"
        # Note: process_auction doesn't return "Level" separately
        assert result["AuctionCheck"] == "Legal"
    
    def test_game_contract(self):
        """Test game-level contract."""
        result = process_auction(Direction.NORTH, "1N-P-3N-P-P-P")
        assert result["DerivedContract"] == "3N"
        # Note: process_auction doesn't return "Level" separately
        assert result["AuctionCheck"] == "Legal"
    
    def test_part_score(self):
        """Test part-score contract."""
        result = process_auction(Direction.NORTH, "1C-P-2C-P-P-P")
        assert result["DerivedContract"] == "2C"
        # Note: process_auction doesn't return "Level" separately
        assert result["AuctionCheck"] == "Legal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



