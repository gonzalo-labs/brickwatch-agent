"""
Company Cost Optimization Policies

Defines cost and compliance guardrails for AWS services. The Brickwatch agent
uses these rules to generate recommendations when telemetry is limited.
"""

COMPANY_COST_POLICIES = {
    "metadata": {
        "company_name": "Brickwatch Demo Corp",
        "policy_version": "2025-Q1",
        "enforcement_level": "strict",  # valid values: strict, advisory, audit
        "effective_date": "2025-01-01",
        "description": "Cost optimization policies to ensure efficient AWS resource usage"
    },
    
    "ec2": {
        "disallowed_instance_types": [
            "r5.*",      # Entire R5 family (memory optimized, higher cost)
            "r5a.*",
            "r5b.*",
            "r5n.*",
            "r6i.*",
            "r6a.*",
            "m5.*",      # Entire M5 family (general purpose, higher cost)
            "m5a.*",
            "m5n.*",
            "m6i.*",
            "c5.*",      # Entire C5 family (compute optimized, higher cost)
            "c5a.*",
            "c5n.*",
            "c6i.*",
            "t2.*",      # Older T2 family (prefer T3)
            "t3.large",
            "t3.xlarge",
            "t3.2xlarge"
        ],
        "recommended_types": ["t3.micro", "t3.small", "t3.medium"],
        "rationale": "Cost optimization - only T3 instance family up to medium size allowed. R5, M5, C5, and T2 families are not approved.",
        "exceptions": {
            "tags": {
                "Environment": ["production", "prod"],
                "CriticalWorkload": ["true"]
            }
        }
    },
    
    "rds": {
        "disallowed_instance_classes": [
            "db.r5.*",
            "db.r5b.*",
            "db.r6i.*",
            "db.m5.*",
            "db.m6i.*"
        ],
        "recommended_classes": ["db.t3.micro", "db.t3.small", "db.t3.medium"],
        "storage": {
            "max_provisioned_iops": 3000,
            "disallowed_storage_types": ["io1", "io2"],  # Provisioned IOPS are costly
            "recommended_storage_type": "gp3",
            "max_allocated_storage_gb": 100
        },
        "rationale": "Database cost optimization - T3 instances are sufficient for most workloads. Use gp3 storage instead of provisioned IOPS.",
        "features": {
            "multi_az": {
                "allowed": False,
                "except_for_tags": ["production", "critical"],
                "rationale": "Multi-AZ doubles cost; reserve for critical workloads"
            },
            "backup_retention_days": {
                "max": 7,
                "recommended": 3,
                "rationale": "Keep backup storage in check"
            }
        }
    },
    
    "lambda": {
        "timeout": {
            "max_seconds": 300,
            "recommended_seconds": 60,
            "rationale": "Most functions should complete within 60s to avoid runaway costs"
        },
        "reserved_concurrency": {
            "max": 100,
            "rationale": "Prevent runaway costs from unlimited scaling"
        }
    },
    
    "ebs": {
        "disallowed_volume_types": ["io1", "io2"],  # Provisioned IOPS are expensive
        "recommended_types": ["gp3"],
        "max_volume_size_gb": 1000,
        "rationale": "gp3 provides good performance at lower cost than provisioned IOPS",
        "unattached_volume_policy": {
            "max_age_days": 7,
            "action": "snapshot_and_delete",
            "rationale": "Unattached volumes waste budget; clean up after 7 days"
        }
    },
    
    "s3": {
        "storage_class": {
            "disallowed": ["STANDARD"],  # Require lifecycle transitions
            "recommended": ["INTELLIGENT_TIERING", "GLACIER_IR"],
            "rationale": "Use Intelligent-Tiering for automatic cost optimization"
        },
        "lifecycle_policy_required": True,
        "versioning": {
            "max_versions": 3,
            "rationale": "Limit versioning bloat; keep only 3 versions"
        }
    },
    
    "elasticache": {
        "disallowed_node_types": [
            "cache.r5.*",
            "cache.r6g.*",
            "cache.m5.*",
            "cache.m6g.*"
        ],
        "recommended_types": ["cache.t3.micro", "cache.t3.small", "cache.t3.medium"],
        "rationale": "T3 cache nodes are sufficient for most caching workloads"
    },
    
    "general": {
        "unused_resources": {
            "check_interval_days": 30,
            "action": "flag_for_deletion",
            "applies_to": ["ebs_volumes", "elastic_ips", "snapshots", "old_amis"],
            "rationale": "Regular cleanup avoids unnecessary spend"
        },
        "tagging_required": {
            "required_tags": ["Environment", "Owner", "CostCenter"],
            "rationale": "Tagging supports allocation and accountability"
        },
        "region_restrictions": {
            "allowed_regions": ["us-east-1", "us-west-2"],
            "rationale": "Standardize regions for pricing and governance"
        }
    }
}


def get_policy(service: str) -> dict:
    """Return the policy for the requested service."""
    return COMPANY_COST_POLICIES.get(service, {})


def get_all_policies() -> dict:
    """Return the full policy registry."""
    return COMPANY_COST_POLICIES


def is_instance_type_allowed(instance_type: str, service: str = "ec2") -> bool:
    """Evaluate whether an instance type passes policy rules."""
    import re
    
    policy = get_policy(service)
    if not policy:
        return True
    
    disallowed = policy.get("disallowed_instance_types", [])
    
    for pattern in disallowed:
        # Convert glob-like pattern to regex
        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
        if re.match(f"^{regex_pattern}$", instance_type):
            return False
    
    return True


def get_recommended_type(current_type: str, service: str = "ec2") -> str:
    """Pick a policy-aligned instance type recommendation."""
    policy = get_policy(service)
    if not policy:
        return current_type
    
    recommended = policy.get("recommended_types", [])
    if recommended:
        # Default to medium size when available
        if "t3.medium" in recommended:
            return "t3.medium"
        return recommended[0] if recommended else current_type
    
    return current_type


def get_policy_rationale(service: str) -> str:
    """Return the policy rationale for a service."""
    policy = get_policy(service)
    return policy.get("rationale", "Company cost optimization policy")
