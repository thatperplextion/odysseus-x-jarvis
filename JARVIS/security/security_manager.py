"""
Jarvis Security Manager - Comprehensive security and permission system
Multi-layered security with granular permission controls and audit logging
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json
import hashlib
import secrets
from cryptography.fernet import Fernet
import hmac

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels"""
    MINIMAL = "minimal"
    STANDARD = "standard"
    HIGH = "high"
    CRITICAL = "critical"


class Permission(Enum):
    """Permission types"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    PROCESS_LIST = "process_list"
    PROCESS_CONTROL = "process_control"
    NETWORK_READ = "network_read"
    NETWORK_WRITE = "network_write"
    SYSTEM_CONFIG = "system_config"
    AUTOMATION_EXECUTE = "automation_execute"
    AUTOMATION_MANAGE = "automation_manage"
    SECURITY_MANAGE = "security_manage"


class ThreatLevel(Enum):
    """Threat severity levels"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    """Represents a security event"""
    id: str
    event_type: str
    severity: ThreatLevel
    source: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False


@dataclass
class PermissionGrant:
    """Represents a permission grant"""
    id: str
    permission: Permission
    scope: str  # e.g., specific path, process, etc.
    granted_to: str  # user or system component
    granted_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    conditions: Dict[str, Any] = field(default_factory=dict)


class PermissionManager:
    """Manages permissions and access control"""
    
    def __init__(self, security_level: SecurityLevel):
        self.security_level = security_level
        self.permission_grants: Dict[str, PermissionGrant] = {}
        self.role_permissions: Dict[str, Set[Permission]] = {}
        
        # Define default permissions per security level
        self._define_default_permissions()
    
    def _define_default_permissions(self):
        """Define default permissions based on security level"""
        if self.security_level == SecurityLevel.MINIMAL:
            self.role_permissions['system'] = {
                Permission.FILE_READ,
                Permission.PROCESS_LIST,
                Permission.NETWORK_READ
            }
        elif self.security_level == SecurityLevel.STANDARD:
            self.role_permissions['system'] = {
                Permission.FILE_READ,
                Permission.FILE_WRITE,
                Permission.PROCESS_LIST,
                Permission.NETWORK_READ,
                Permission.AUTOMATION_EXECUTE
            }
        elif self.security_level == SecurityLevel.HIGH:
            self.role_permissions['system'] = {
                Permission.FILE_READ,
                Permission.FILE_WRITE,
                Permission.FILE_DELETE,
                Permission.PROCESS_LIST,
                Permission.PROCESS_CONTROL,
                Permission.NETWORK_READ,
                Permission.NETWORK_WRITE,
                Permission.AUTOMATION_EXECUTE,
                Permission.AUTOMATION_MANAGE
            }
        elif self.security_level == SecurityLevel.CRITICAL:
            self.role_permissions['system'] = {
                Permission.FILE_READ,
                Permission.FILE_WRITE,
                Permission.FILE_DELETE,
                Permission.PROCESS_LIST,
                Permission.PROCESS_CONTROL,
                Permission.NETWORK_READ,
                Permission.NETWORK_WRITE,
                Permission.SYSTEM_CONFIG,
                Permission.AUTOMATION_EXECUTE,
                Permission.AUTOMATION_MANAGE,
                Permission.SECURITY_MANAGE
            }
    
    def check_permission(self, entity: str, permission: Permission, 
                        scope: str = None) -> bool:
        """Check if an entity has a specific permission"""
        # Check role permissions
        if entity in self.role_permissions:
            if permission in self.role_permissions[entity]:
                # Check scope if provided
                if scope:
                    # Check if there's a specific grant for this scope
                    for grant in self.permission_grants.values():
                        if (grant.granted_to == entity and 
                            grant.permission == permission and
                            grant.scope == scope):
                            # Check if grant is expired
                            if grant.expires_at and datetime.now() > grant.expires_at:
                                return False
                            # Check conditions
                            if not self._check_conditions(grant.conditions):
                                return False
                            return True
                    # No specific grant, deny scoped access
                    return False
                return True
        
        # Check specific grants
        for grant in self.permission_grants.values():
            if (grant.granted_to == entity and 
                grant.permission == permission):
                
                if scope and grant.scope != scope:
                    continue
                
                if grant.expires_at and datetime.now() > grant.expires_at:
                    continue
                
                if not self._check_conditions(grant.conditions):
                    continue
                
                return True
        
        return False
    
    def _check_conditions(self, conditions: Dict[str, Any]) -> bool:
        """Check if conditions for a permission grant are met"""
        # Simple condition checking
        # In production, this would be more sophisticated
        for key, value in conditions.items():
            if key == 'time_range':
                current_hour = datetime.now().hour
                if not (value['start'] <= current_hour <= value['end']):
                    return False
            elif key == 'max_uses':
                # Would need to track usage
                pass
        
        return True
    
    def grant_permission(self, entity: str, permission: Permission, 
                        scope: str = None, expires_in_hours: int = None,
                        conditions: Dict[str, Any] = None) -> str:
        """Grant a permission to an entity"""
        grant_id = f"grant_{secrets.token_hex(8)}"
        
        expires_at = None
        if expires_in_hours:
            expires_at = datetime.now() + timedelta(hours=expires_in_hours)
        
        grant = PermissionGrant(
            id=grant_id,
            permission=permission,
            scope=scope or "*",
            granted_to=entity,
            expires_at=expires_at,
            conditions=conditions or {}
        )
        
        self.permission_grants[grant_id] = grant
        
        logger.info(f"Granted permission {permission.value} to {entity}")
        return grant_id
    
    def revoke_permission(self, grant_id: str) -> bool:
        """Revoke a permission grant"""
        if grant_id in self.permission_grants:
            del self.permission_grants[grant_id]
            logger.info(f"Revoked permission grant {grant_id}")
            return True
        return False


class AuditLogger:
    """Logs all security-relevant events"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.audit_file = data_dir / "security_audit.log"
        self.events: List[SecurityEvent] = []
        self.max_events = 10000
    
    def log_event(self, event_type: str, severity: ThreatLevel, 
                 source: str, details: Dict[str, Any] = None):
        """Log a security event"""
        event = SecurityEvent(
            id=f"evt_{secrets.token_hex(8)}",
            event_type=event_type,
            severity=severity,
            source=source,
            details=details or {}
        )
        
        self.events.append(event)
        
        # Trim events
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
        
        # Write to file
        self._write_to_file(event)
        
        # Log to standard logger
        log_func = {
            ThreatLevel.INFO: logger.info,
            ThreatLevel.LOW: logger.warning,
            ThreatLevel.MEDIUM: logger.warning,
            ThreatLevel.HIGH: logger.error,
            ThreatLevel.CRITICAL: logger.critical
        }.get(severity, logger.info)
        
        log_func(f"Security event: {event_type} - {details}")
    
    def _write_to_file(self, event: SecurityEvent):
        """Write event to audit file"""
        try:
            with open(self.audit_file, 'a') as f:
                log_entry = {
                    'id': event.id,
                    'type': event.event_type,
                    'severity': event.severity.value,
                    'source': event.source,
                    'details': event.details,
                    'timestamp': event.timestamp.isoformat()
                }
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}", exc_info=True)
    
    def get_events(self, severity: ThreatLevel = None, 
                  limit: int = 100) -> List[SecurityEvent]:
        """Get security events"""
        events = self.events
        
        if severity:
            events = [e for e in events if e.severity == severity]
        
        return events[-limit:]


class ThreatDetector:
    """Detects security threats and anomalies"""
    
    def __init__(self, audit_logger: AuditLogger):
        self.audit_logger = audit_logger
        self.baseline_metrics: Dict[str, Any] = {}
        self.anomaly_thresholds = {
            'failed_auth_attempts': 5,
            'suspicious_file_access': 10,
            'unusual_process_activity': 3
        }
        self.counters: Dict[str, int] = {}
    
    def analyze_event(self, event: SecurityEvent) -> Optional[ThreatLevel]:
        """Analyze a security event for threats"""
        threat_level = None
        
        # Check for authentication failures
        if event.event_type == 'auth_failure':
            key = f"auth_fail_{event.source}"
            self.counters[key] = self.counters.get(key, 0) + 1
            
            if self.counters[key] >= self.anomaly_thresholds['failed_auth_attempts']:
                threat_level = ThreatLevel.HIGH
                self.audit_logger.log_event(
                    'brute_force_detected',
                    ThreatLevel.HIGH,
                    'threat_detector',
                    {'source': event.source, 'attempts': self.counters[key]}
                )
        
        # Check for suspicious file access
        if event.event_type == 'file_access_denied':
            key = f"file_denied_{event.source}"
            self.counters[key] = self.counters.get(key, 0) + 1
            
            if self.counters[key] >= self.anomaly_thresholds['suspicious_file_access']:
                threat_level = ThreatLevel.MEDIUM
                self.audit_logger.log_event(
                    'suspicious_file_activity',
                    ThreatLevel.MEDIUM,
                    'threat_detector',
                    {'source': event.source, 'denials': self.counters[key]}
                )
        
        # Check for unusual process activity
        if event.event_type == 'process_termination':
            key = f"process_term_{event.source}"
            self.counters[key] = self.counters.get(key, 0) + 1
            
            if self.counters[key] >= self.anomaly_thresholds['unusual_process_activity']:
                threat_level = ThreatLevel.MEDIUM
                self.audit_logger.log_event(
                    'unusual_process_activity',
                    ThreatLevel.MEDIUM,
                    'threat_detector',
                    {'source': event.source, 'terminations': self.counters[key]}
                )
        
        return threat_level
    
    def reset_counters(self):
        """Reset anomaly counters"""
        self.counters.clear()


class CredentialManager:
    """Manages secure credential storage"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.key_file = data_dir / "encryption.key"
        self.credentials_file = data_dir / "credentials.enc"
        self.cipher: Optional[Fernet] = None
        self.credentials: Dict[str, str] = {}
        
        self._initialize()
    
    def _initialize(self):
        """Initialize encryption"""
        # Load or generate encryption key
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Set restrictive permissions
            os.chmod(self.key_file, 0o600)
        
        self.cipher = Fernet(key)
        
        # Load existing credentials
        if self.credentials_file.exists():
            self._load_credentials()
    
    def _load_credentials(self):
        """Load encrypted credentials"""
        try:
            with open(self.credentials_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            self.credentials = json.loads(decrypted_data.decode())
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}", exc_info=True)
    
    def _save_credentials(self):
        """Save encrypted credentials"""
        try:
            data = json.dumps(self.credentials).encode()
            encrypted_data = self.cipher.encrypt(data)
            
            with open(self.credentials_file, 'wb') as f:
                f.write(encrypted_data)
            
            os.chmod(self.credentials_file, 0o600)
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}", exc_info=True)
    
    def store_credential(self, name: str, value: str) -> bool:
        """Store a credential securely"""
        try:
            self.credentials[name] = value
            self._save_credentials()
            logger.info(f"Stored credential: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to store credential: {e}", exc_info=True)
            return False
    
    def retrieve_credential(self, name: str) -> Optional[str]:
        """Retrieve a credential"""
        return self.credentials.get(name)
    
    def delete_credential(self, name: str) -> bool:
        """Delete a credential"""
        if name in self.credentials:
            del self.credentials[name]
            self._save_credentials()
            logger.info(f"Deleted credential: {name}")
            return True
        return False


class SecurityManager:
    """Main security manager - coordinates all security components"""
    
    def __init__(self, security_level: str, data_dir: Path):
        self.data_dir = data_dir
        self.state = "initializing"
        
        # Parse security level
        try:
            self.security_level = SecurityLevel(security_level)
        except ValueError:
            self.security_level = SecurityLevel.STANDARD
            logger.warning(f"Invalid security level '{security_level}', using STANDARD")
        
        # Initialize components
        self.permission_manager = PermissionManager(self.security_level)
        self.audit_logger = AuditLogger(data_dir)
        self.threat_detector = ThreatDetector(self.audit_logger)
        self.credential_manager = CredentialManager(data_dir)
        
        # Security metrics
        self.metrics = {
            'total_events': 0,
            'threats_detected': 0,
            'auth_failures': 0,
            'permission_denials': 0
        }
        
        logger.info(f"Security manager initialized with level: {self.security_level.value}")
    
    async def initialize(self):
        """Initialize security manager"""
        logger.info("Initializing security manager...")
        
        # Start threat monitoring
        asyncio.create_task(self._monitor_threats())
        
        self.state = "running"
        logger.info("Security manager ready")
    
    def check_permission(self, entity: str, permission: Permission, 
                        scope: str = None) -> bool:
        """Check if an entity has permission"""
        allowed = self.permission_manager.check_permission(entity, permission, scope)
        
        if not allowed:
            self.metrics['permission_denials'] += 1
            self.audit_logger.log_event(
                'permission_denied',
                ThreatLevel.LOW,
                entity,
                {'permission': permission.value, 'scope': scope}
            )
        
        return allowed
    
    def grant_permission(self, entity: str, permission: Permission, 
                        scope: str = None, expires_in_hours: int = None,
                        conditions: Dict[str, Any] = None) -> str:
        """Grant a permission"""
        grant_id = self.permission_manager.grant_permission(
            entity, permission, scope, expires_in_hours, conditions
        )
        
        self.audit_logger.log_event(
            'permission_granted',
            ThreatLevel.INFO,
            'security_manager',
            {'entity': entity, 'permission': permission.value, 'grant_id': grant_id}
        )
        
        return grant_id
    
    def revoke_permission(self, grant_id: str) -> bool:
        """Revoke a permission"""
        revoked = self.permission_manager.revoke_permission(grant_id)
        
        if revoked:
            self.audit_logger.log_event(
                'permission_revoked',
                ThreatLevel.INFO,
                'security_manager',
                {'grant_id': grant_id}
            )
        
        return revoked
    
    def log_security_event(self, event_type: str, severity: ThreatLevel,
                         source: str, details: Dict[str, Any] = None):
        """Log a security event"""
        self.metrics['total_events'] += 1
        
        event = SecurityEvent(
            id=f"evt_{secrets.token_hex(8)}",
            event_type=event_type,
            severity=severity,
            source=source,
            details=details or {}
        )
        
        self.audit_logger.log_event(event_type, severity, source, details)
        
        # Analyze for threats
        threat_level = self.threat_detector.analyze_event(event)
        if threat_level and threat_level.value in ['high', 'critical']:
            self.metrics['threats_detected'] += 1
    
    async def _monitor_threats(self):
        """Monitor for security threats"""
        while self.state == "running":
            try:
                # Periodically reset counters
                self.threat_detector.reset_counters()
                
                await asyncio.sleep(300)  # Reset every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in threat monitoring: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    def store_credential(self, name: str, value: str) -> bool:
        """Store a credential"""
        return self.credential_manager.store_credential(name, value)
    
    def retrieve_credential(self, name: str) -> Optional[str]:
        """Retrieve a credential"""
        return self.credential_manager.retrieve_credential(name)
    
    def get_security_events(self, severity: ThreatLevel = None,
                           limit: int = 100) -> List[SecurityEvent]:
        """Get security events"""
        return self.audit_logger.get_events(severity, limit)
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            # Check if we can store/retrieve credentials
            test_name = f"test_{secrets.token_hex(4)}"
            if self.credential_manager.store_credential(test_name, "test_value"):
                if self.credential_manager.retrieve_credential(test_name) == "test_value":
                    self.credential_manager.delete_credential(test_name)
                    return "healthy"
            
            return "unhealthy: credential manager test failed"
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get security manager status"""
        return {
            'state': self.state,
            'security_level': self.security_level.value,
            'metrics': self.metrics,
            'permission_grants': len(self.permission_manager.permission_grants),
            'stored_credentials': len(self.credential_manager.credentials)
        }
    
    async def shutdown(self):
        """Shutdown security manager"""
        logger.info("Shutting down security manager...")
        self.state = "shutting_down"
        
        # Save any pending data
        self.credential_manager._save_credentials()
        
        logger.info("Security manager shutdown complete")
