"""
CSV loaders for OmniSupply.

Stubbed. The original loaders were excluded from the repo (.gitignore matched
src/data/). Filling these in requires the four Kaggle CSVs listed in SETUP_GUIDE.md
and mapping their columns to the Pydantic models in src/data/models.py.

Only omnisupply_demo.py calls into this module. The Streamlit app (app.py) does
not import it, so deploying with the stub is fine — the demo will raise a clear
error if invoked without a real implementation.
"""
from pathlib import Path
from typing import Any, Dict, List

from ..models import FinancialTransaction, InventoryItem, Order, Shipment


class OmniSupplyDataLoader:
    """Loads the four supply-chain CSVs into Pydantic model lists.

    Expected files in `data_dir`:
      - DataCoSupplyChainDataset.csv
      - dynamic_supply_chain_logistics_dataset.csv
      - supply_chain_data.csv
      - Retail-Supply-Chain-Sales-Dataset.xlsx
    """

    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)

    def load_all(self) -> Dict[str, List[Any]]:
        raise NotImplementedError(
            "OmniSupplyDataLoader.load_all() was not committed to the repo. "
            "Implement the CSV-to-Pydantic mapping in src/data/ingestion/loaders.py "
            "before running omnisupply_demo.py. The Streamlit app (app.py) does "
            "not require this; it works against an empty PostgreSQL database."
        )

    def load_orders(self) -> List[Order]:
        raise NotImplementedError

    def load_shipments(self) -> List[Shipment]:
        raise NotImplementedError

    def load_inventory(self) -> List[InventoryItem]:
        raise NotImplementedError

    def load_transactions(self) -> List[FinancialTransaction]:
        raise NotImplementedError
