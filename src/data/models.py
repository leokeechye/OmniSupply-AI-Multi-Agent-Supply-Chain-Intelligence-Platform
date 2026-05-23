"""
Pydantic domain models for OmniSupply.

These mirror the SQLAlchemy ORM models in src/storage/sql/models.py and are the
shape that DatabaseClient.insert_* methods expect. AgentResult is the return
contract every agent's .execute() satisfies and that SupervisorAgent aggregates.

Reconstructed because the original src/data/ directory was excluded from the
repo by .gitignore (bare pattern `data/` matched src/data/ too). Field names
and types are derived from src/storage/sql/models.py and the kwargs used in
DatabaseClient.insert_orders/insert_shipments/insert_inventory/insert_transactions.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


_ALLOW_NUMERIC = ConfigDict(arbitrary_types_allowed=True)


class Order(BaseModel):
    model_config = _ALLOW_NUMERIC

    order_id: str
    order_date: datetime
    ship_mode: Optional[str] = None
    segment: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    region: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    product_id: Optional[str] = None
    cost_price: Optional[Decimal] = None
    list_price: Optional[Decimal] = None
    quantity: Optional[int] = None
    discount_percent: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    is_returned: bool = False


class Shipment(BaseModel):
    model_config = _ALLOW_NUMERIC

    shipment_id: str
    product_id: Optional[str] = None
    origin_port: Optional[str] = None
    destination_port: Optional[str] = None
    carrier: Optional[str] = None
    shipment_date: datetime
    expected_delivery: datetime
    actual_delivery: Optional[datetime] = None
    quantity: Optional[int] = None
    weight_kg: Optional[Decimal] = None
    freight_cost: Optional[Decimal] = None
    insurance_cost: Optional[Decimal] = None
    customs_cost: Optional[Decimal] = None
    status: Optional[str] = None
    delay_reason: Optional[str] = None


class InventoryItem(BaseModel):
    model_config = _ALLOW_NUMERIC

    sku: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    warehouse_location: Optional[str] = None
    stock_quantity: int
    reorder_level: Optional[int] = None
    reorder_quantity: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    last_restock_date: Optional[datetime] = None
    lead_time_days: Optional[int] = None
    supplier_id: Optional[str] = None


class FinancialTransaction(BaseModel):
    model_config = _ALLOW_NUMERIC

    transaction_id: str
    transaction_date: datetime
    transaction_type: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    amount: Decimal
    currency: str = "USD"
    cost_center: Optional[str] = None
    business_unit: Optional[str] = None
    payment_method: Optional[str] = None
    vendor_id: Optional[str] = None
    notes: Optional[str] = None


class AgentResult(BaseModel):
    """Return contract for every agent's .execute() call.

    SupervisorAgent reads .success, .insights, .recommendations, .metrics, .error.
    BaseAgent mutates .execution_time_ms after construction, so the model is not
    frozen.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_name: str
    query: str
    timestamp: datetime
    success: bool = True
    insights: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None
    raw_output: Optional[Dict[str, Any]] = None


class RiskAssessment(BaseModel):
    """Placeholder. risk_agent.py imports this name but uses a locally-defined
    OverallRiskAssessment for actual structured output. Keeping the symbol so
    `from ..data.models import AgentResult, RiskAssessment` resolves."""
    severity: str = "INFO"
    title: str = ""
    description: str = ""
    affected_entities: List[str] = Field(default_factory=list)
