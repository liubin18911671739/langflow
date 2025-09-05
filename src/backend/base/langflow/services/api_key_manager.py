"""Enhanced API key management system with rotation and security features"""
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, validator
from fastapi import HTTPException, status
from loguru import logger

from langflow.services.deps import get_settings_service
from langflow.services.database.models.api_key.model import ApiKey


class ApiKeyStatus(str, Enum):
    """API key status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING_ROTATION = "pending_rotation"


class ApiKeyPermission(str, Enum):
    """API key permission levels"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ApiKeyCreateRequest(BaseModel):
    """Request model for creating API key"""
    name: str = Field(..., min_length=3, max_length=100, description="API key name")
    description: Optional[str] = Field(None, max_length=500, description="API key description")
    permissions: List[ApiKeyPermission] = Field([ApiKeyPermission.READ], description="API key permissions")
    expires_at: Optional[datetime] = Field(None, description="API key expiration date")
    allowed_ips: Optional[List[str]] = Field(None, description="Allowed IP addresses")
    allowed_referers: Optional[List[str]] = Field(None, description="Allowed referers")
    
    @validator('expires_at')
    def validate_expiration(cls, v):
        if v and v <= datetime.utcnow():
            raise ValueError("Expiration date must be in the future")
        return v
    
    @validator('allowed_ips')
    def validate_ips(cls, v):
        if v:
            for ip in v:
                if not self._is_valid_ip(ip):
                    raise ValueError(f"Invalid IP address: {ip}")
        return v
    
    @validator('allowed_referers')
    def validate_referers(cls, v):
        if v:
            for referer in v:
                if not referer.startswith(('http://', 'https://')):
                    raise ValueError(f"Invalid referer: {referer}")
        return v
    
    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """Simple IP validation"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False


class ApiKeyResponse(BaseModel):
    """Response model for API key"""
    id: UUID
    name: str
    description: Optional[str]
    permissions: List[ApiKeyPermission]
    status: ApiKeyStatus
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int
    allowed_ips: Optional[List[str]]
    allowed_referers: Optional[List[str]]


class ApiKeyWithSecret(ApiKeyResponse):
    """Response model with API key secret (only shown on creation)"""
    api_key: str
    api_key_secret: str


class ApiKeyRotationRequest(BaseModel):
    """Request model for rotating API key"""
    reason: str = Field(..., min_length=3, max_length=200, description="Reason for rotation")
    immediate_revoke: bool = Field(False, description="Revoke old key immediately")


class ApiKeyManager:
    """Enhanced API key management system"""
    
    def __init__(self):
        self.settings = get_settings_service().settings
        self.api_key_prefix = "lf_"
        self.min_key_length = 32
        self.max_key_length = 64
        
    async def create_api_key(
        self,
        user_id: UUID,
        request: ApiKeyCreateRequest
    ) -> ApiKeyWithSecret:
        """Create a new API key with enhanced security"""
        
        # Generate secure API key pair
        api_key, api_key_secret = self._generate_api_key_pair()
        
        # Hash the secret for storage
        secret_hash = self._hash_secret(api_key_secret)
        
        # Create API key record
        api_key_record = ApiKey(
            user_id=user_id,
            name=request.name,
            description=request.description,
            api_key_prefix=api_key[:8],  # Store prefix for identification
            api_key_hash=self._hash_key(api_key),
            api_key_secret_hash=secret_hash,
            permissions=[p.value for p in request.permissions],
            status=ApiKeyStatus.ACTIVE,
            expires_at=request.expires_at,
            allowed_ips=request.allowed_ips,
            allowed_referers=request.allowed_referers,
            created_at=datetime.utcnow(),
            usage_count=0
        )
        
        # Store in database
        from langflow.services.database.models.api_key.crud import create_api_key as db_create_key
        created_key = await db_create_key(None, api_key_record, user_id=user_id)
        
        # Return response with secret (only shown once)
        return ApiKeyWithSecret(
            id=created_key.id,
            name=created_key.name,
            description=created_key.description,
            permissions=[ApiKeyPermission(p) for p in created_key.permissions],
            status=created_key.status,
            created_at=created_key.created_at,
            expires_at=created_key.expires_at,
            last_used_at=created_key.last_used_at,
            usage_count=created_key.usage_count,
            allowed_ips=created_key.allowed_ips,
            allowed_referers=created_key.allowed_referers,
            api_key=api_key,
            api_key_secret=api_key_secret
        )
    
    async def rotate_api_key(
        self,
        api_key_id: UUID,
        user_id: UUID,
        request: ApiKeyRotationRequest
    ) -> ApiKeyWithSecret:
        """Rotate an existing API key"""
        
        # Get existing key
        from langflow.services.database.models.api_key.crud import get_api_key_by_id
        existing_key = await get_api_key_by_id(None, api_key_id, user_id)
        
        if not existing_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        # Generate new key pair
        new_api_key, new_api_key_secret = self._generate_api_key_pair()
        new_secret_hash = self._hash_secret(new_api_key_secret)
        
        # Update key record
        existing_key.api_key_prefix = new_api_key[:8]
        existing_key.api_key_hash = self._hash_key(new_api_key)
        existing_key.api_key_secret_hash = new_secret_hash
        existing_key.last_rotated_at = datetime.utcnow()
        existing_key.rotation_reason = request.reason
        
        if request.immediate_revoke:
            existing_key.status = ApiKeyStatus.REVOKED
        else:
            existing_key.status = ApiKeyStatus.PENDING_ROTATION
        
        # Save changes
        from langflow.services.database.models.api_key.crud import update_api_key
        updated_key = await update_api_key(None, existing_key)
        
        # Return new key details
        return ApiKeyWithSecret(
            id=updated_key.id,
            name=updated_key.name,
            description=updated_key.description,
            permissions=[ApiKeyPermission(p) for p in updated_key.permissions],
            status=updated_key.status,
            created_at=updated_key.created_at,
            expires_at=updated_key.expires_at,
            last_used_at=updated_key.last_used_at,
            usage_count=updated_key.usage_count,
            allowed_ips=updated_key.allowed_ips,
            allowed_referers=updated_key.allowed_referers,
            api_key=new_api_key,
            api_key_secret=new_api_key_secret
        )
    
    async def validate_api_key(
        self,
        api_key: str,
        api_key_secret: str,
        request_ip: Optional[str] = None,
        request_referer: Optional[str] = None
    ) -> Optional[ApiKey]:
        """Validate API key with enhanced security checks"""
        
        # Extract prefix from API key
        if not api_key.startswith(self.api_key_prefix):
            return None
        
        prefix = api_key[:8]
        
        # Get API key from database
        from langflow.services.database.models.api_key.crud import get_api_key_by_prefix
        api_key_record = await get_api_key_by_prefix(None, prefix)
        
        if not api_key_record:
            return None
        
        # Verify key hash
        if not self._verify_key(api_key, api_key_record.api_key_hash):
            return None
        
        # Verify secret hash
        if not self._verify_secret(api_key_secret, api_key_record.api_key_secret_hash):
            return None
        
        # Check status
        if api_key_record.status == ApiKeyStatus.REVOKED:
            return None
        
        if api_key_record.status == ApiKeyStatus.EXPIRED:
            return None
        
        # Check expiration
        if api_key_record.expires_at and api_key_record.expires_at <= datetime.utcnow():
            api_key_record.status = ApiKeyStatus.EXPIRED
            await self._update_api_key_status(api_key_record.id, ApiKeyStatus.EXPIRED)
            return None
        
        # Check IP restrictions
        if api_key_record.allowed_ips and request_ip:
            if request_ip not in api_key_record.allowed_ips:
                logger.warning(f"API key access from unauthorized IP: {request_ip}")
                return None
        
        # Check referer restrictions
        if api_key_record.allowed_referers and request_referer:
            if not any(request_referer.startswith(ref) for ref in api_key_record.allowed_referers):
                logger.warning(f"API key access from unauthorized referer: {request_referer}")
                return None
        
        # Update usage statistics
        await self._update_api_key_usage(api_key_record.id)
        
        return api_key_record
    
    async def revoke_api_key(self, api_key_id: UUID, user_id: UUID) -> bool:
        """Revoke an API key"""
        
        from langflow.services.database.models.api_key.crud import get_api_key_by_id
        api_key_record = await get_api_key_by_id(None, api_key_id, user_id)
        
        if not api_key_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        api_key_record.status = ApiKeyStatus.REVOKED
        api_key_record.revoked_at = datetime.utcnow()
        
        from langflow.services.database.models.api_key.crud import update_api_key
        await update_api_key(None, api_key_record)
        
        return True
    
    async def cleanup_expired_keys(self) -> int:
        """Clean up expired API keys"""
        
        from langflow.services.database.models.api_key.crud import get_expired_api_keys
        expired_keys = await get_expired_api_keys(None)
        
        count = 0
        for key in expired_keys:
            key.status = ApiKeyStatus.EXPIRED
            from langflow.services.database.models.api_key.crud import update_api_key
            await update_api_key(None, key)
            count += 1
        
        logger.info(f"Cleaned up {count} expired API keys")
        return count
    
    def _generate_api_key_pair(self) -> tuple[str, str]:
        """Generate secure API key pair"""
        
        # Generate API key
        api_key = self.api_key_prefix + secrets.token_urlsafe(32)
        
        # Generate API secret
        api_secret = secrets.token_urlsafe(48)
        
        return api_key, api_secret
    
    def _hash_key(self, api_key: str) -> str:
        """Hash API key for storage"""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def _hash_secret(self, api_secret: str) -> str:
        """Hash API secret for storage"""
        return hashlib.sha512(api_secret.encode()).hexdigest()
    
    def _verify_key(self, api_key: str, key_hash: str) -> bool:
        """Verify API key hash"""
        return hmac.compare_digest(self._hash_key(api_key), key_hash)
    
    def _verify_secret(self, api_secret: str, secret_hash: str) -> bool:
        """Verify API secret hash"""
        return hmac.compare_digest(self._hash_secret(api_secret), secret_hash)
    
    async def _update_api_key_usage(self, api_key_id: UUID):
        """Update API key usage statistics"""
        
        from langflow.services.database.models.api_key.crud import increment_api_key_usage
        await increment_api_key_usage(None, api_key_id)
    
    async def _update_api_key_status(self, api_key_id: UUID, status: ApiKeyStatus):
        """Update API key status"""
        
        from langflow.services.database.models.api_key.crud import update_api_key_status
        await update_api_key_status(None, api_key_id, status)


# Global instance
api_key_manager = ApiKeyManager()


async def get_api_key_manager() -> ApiKeyManager:
    """Get API key manager instance"""
    return api_key_manager