"""
Alert configuration and history endpoints for AlphaCent Trading Platform.

Provides endpoints for managing alert preferences and viewing alert history.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.models.orm import AlertConfigORM, AlertHistoryORM
from src.models.database import Database
from src.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertConfigRequest(BaseModel):
    """Alert configuration update request."""
    pnl_loss_enabled: bool = False
    pnl_loss_threshold: float = Field(default=1000.0, ge=0)
    pnl_gain_enabled: bool = False
    pnl_gain_threshold: float = Field(default=5000.0, ge=0)
    drawdown_enabled: bool = True
    drawdown_threshold: float = Field(default=10.0, ge=0, le=100)
    position_loss_enabled: bool = True
    position_loss_threshold: float = Field(default=5.0, ge=0, le=100)
    margin_enabled: bool = False
    margin_threshold: float = Field(default=80.0, ge=0, le=100)
    cycle_complete_enabled: bool = True
    strategy_retired_enabled: bool = True
    browser_push_enabled: bool = False


class AlertConfigResponse(BaseModel):
    """Alert configuration response."""
    success: bool
    data: Dict[str, Any]


class AlertHistoryResponse(BaseModel):
    """Alert history response."""
    success: bool
    data: Dict[str, Any]


@router.get("/config")
async def get_alert_config(user: dict = Depends(get_current_user)):
    """Get current alert configuration."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            config = session.query(AlertConfigORM).first()
            if not config:
                # Create default config
                config = AlertConfigORM()
                session.add(config)
                session.commit()
                session.refresh(config)
            return {"success": True, "data": config.to_dict()}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting alert config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def update_alert_config(
    request: AlertConfigRequest,
    user: dict = Depends(get_current_user),
):
    """Update alert configuration."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            config = session.query(AlertConfigORM).first()
            if not config:
                config = AlertConfigORM()
                session.add(config)

            config.pnl_loss_enabled = request.pnl_loss_enabled
            config.pnl_loss_threshold = request.pnl_loss_threshold
            config.pnl_gain_enabled = request.pnl_gain_enabled
            config.pnl_gain_threshold = request.pnl_gain_threshold
            config.drawdown_enabled = request.drawdown_enabled
            config.drawdown_threshold = request.drawdown_threshold
            config.position_loss_enabled = request.position_loss_enabled
            config.position_loss_threshold = request.position_loss_threshold
            config.margin_enabled = request.margin_enabled
            config.margin_threshold = request.margin_threshold
            config.cycle_complete_enabled = request.cycle_complete_enabled
            config.strategy_retired_enabled = request.strategy_retired_enabled
            config.browser_push_enabled = request.browser_push_enabled

            session.commit()
            session.refresh(config)
            return {"success": True, "data": config.to_dict()}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error updating alert config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_alert_history(
    limit: int = 50,
    unread_only: bool = False,
    severity: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Get alert history with optional filters."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            query = session.query(AlertHistoryORM).order_by(AlertHistoryORM.created_at.desc())
            if unread_only:
                query = query.filter(AlertHistoryORM.read == False)
            if severity:
                query = query.filter(AlertHistoryORM.severity == severity)
            alerts = query.limit(limit).all()
            unread_count = session.query(AlertHistoryORM).filter(AlertHistoryORM.read == False).count()
            return {
                "success": True,
                "data": {
                    "alerts": [a.to_dict() for a in alerts],
                    "unread_count": unread_count,
                    "total": len(alerts),
                },
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/history/{alert_id}/read")
async def mark_alert_read(alert_id: int, user: dict = Depends(get_current_user)):
    """Mark a single alert as read."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            alert = session.query(AlertHistoryORM).filter(AlertHistoryORM.id == alert_id).first()
            if not alert:
                raise HTTPException(status_code=404, detail="Alert not found")
            alert.read = True
            session.commit()
            return {"success": True}
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking alert read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/history/read-all")
async def mark_all_alerts_read(user: dict = Depends(get_current_user)):
    """Mark all alerts as read."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            session.query(AlertHistoryORM).filter(AlertHistoryORM.read == False).update({"read": True})
            session.commit()
            return {"success": True}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error marking all alerts read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/history/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, user: dict = Depends(get_current_user)):
    """Acknowledge a critical alert."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            alert = session.query(AlertHistoryORM).filter(AlertHistoryORM.id == alert_id).first()
            if not alert:
                raise HTTPException(status_code=404, detail="Alert not found")
            alert.acknowledged = True
            alert.read = True
            session.commit()
            return {"success": True}
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history")
async def clear_alert_history(user: dict = Depends(get_current_user)):
    """Clear all alert history."""
    try:
        db = Database()
        session = db.SessionLocal()
        try:
            session.query(AlertHistoryORM).delete()
            session.commit()
            return {"success": True}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error clearing alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
