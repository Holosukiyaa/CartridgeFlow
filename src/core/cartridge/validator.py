import json
from pathlib import Path

from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.cartridge.assets import CartridgeAssetError, load_asset_bundle, validate_interaction_nodes


class ManifestValidationError(ValueError):
    pass


class ManifestValidator:
    REQUIRED_STRING_FIELDS = ["schema_version", "id", "name", "version", "kind", "category"]
    LLM_RECIPE_LOCAL_FIELDS = {
        "api_key",
        "authorization",
        "base_url",
        "command",
        "args",
        "endpoint",
        "headers",
        "location",
        "openapi_url",
        "auth_env",
        "key",
        "secret",
        "token",
        "url",
    }

    def validate_package(self, package_path: Path, manifest: dict) -> dict:
        errors = []
        for field in self.REQUIRED_STRING_FIELDS:
            if not isinstance(manifest.get(field), str) or not manifest.get(field).strip():
                errors.append(f"manifest.{field} is required")

        if not isinstance(manifest.get("runtime"), dict):
            errors.append("manifest.runtime must be an object")
        elif not manifest["runtime"].get("type"):
            errors.append("manifest.runtime.type is required")

        base_contract = manifest.get("base_contract")
        if base_contract is not None:
            if not isinstance(base_contract, dict):
                errors.append("manifest.base_contract must be an object")
            else:
                if not isinstance(base_contract.get("id"), str) or not base_contract.get("id").strip():
                    errors.append("manifest.base_contract.id is required")
                if not isinstance(base_contract.get("version"), str) or not base_contract.get("version").strip():
                    errors.append("manifest.base_contract.version is required")

        runtime_contract = manifest.get("runtime_contract")
        if runtime_contract is not None:
            if not isinstance(runtime_contract, dict):
                errors.append("manifest.runtime_contract must be an object")
            else:
                if not isinstance(runtime_contract.get("protocol"), str) or not runtime_contract.get("protocol").strip():
                    errors.append("manifest.runtime_contract.protocol is required")
                if not isinstance(runtime_contract.get("protocol_version"), str) or not runtime_contract.get("protocol_version").strip():
                    errors.append("manifest.runtime_contract.protocol_version is required")
                for field in [
                    "required_profiles",
                    "recommended_profiles",
                    "required_capabilities",
                    "optional_capabilities",
                    "required_tools",
                    "optional_tools",
                ]:
                    value = runtime_contract.get(field, [])
                    if not isinstance(value, list):
                        errors.append(f"manifest.runtime_contract.{field} must be an array")
                    else:
                        for i, item in enumerate(value):
                            if isinstance(item, str):
                                if not item.strip():
                                    errors.append(f"manifest.runtime_contract.{field}[{i}] must not be empty")
                            elif isinstance(item, dict):
                                if not item.get("id"):
                                    errors.append(f"manifest.runtime_contract.{field}[{i}].id is required")
                            else:
                                errors.append(f"manifest.runtime_contract.{field}[{i}] must be a string or object")

        runtime_protocol = runtime_contract if isinstance(runtime_contract, dict) else {}
        is_v06 = runtime_protocol.get("protocol") == "CF-FARP" and runtime_protocol.get("protocol_version") == "0.6"
        is_v07 = runtime_protocol.get("protocol") == "CF-FARP" and runtime_protocol.get("protocol_version") == "0.7"
        if is_v06 or is_v07:
            base_contract = manifest.get("base_contract")
            if not isinstance(base_contract, dict) or base_contract.get("id") != "CARTRIDGEFLOW-BASE" or not base_contract.get("version"):
                errors.append(f"CF-FARP@{'0.7' if is_v07 else '0.6'} requires manifest.base_contract with id CARTRIDGEFLOW-BASE and a version")

        protocol_extensions = manifest.get("protocol_extensions", [])
        if not isinstance(protocol_extensions, list):
            errors.append("manifest.protocol_extensions must be an array")
        else:
            for i, extension in enumerate(protocol_extensions):
                if not isinstance(extension, dict):
                    errors.append(f"manifest.protocol_extensions[{i}] must be an object")
                    continue
                for field in ["id", "version"]:
                    if not isinstance(extension.get(field), str) or not extension.get(field).strip():
                        errors.append(f"manifest.protocol_extensions[{i}].{field} is required")
                extends = extension.get("extends")
                if extends is not None:
                    if not isinstance(extends, dict):
                        errors.append(f"manifest.protocol_extensions[{i}].extends must be an object")
                    else:
                        for field in ["id", "version"]:
                            if not isinstance(extends.get(field), str) or not extends.get(field).strip():
                                errors.append(f"manifest.protocol_extensions[{i}].extends.{field} is required")
                for field in ["required_profiles", "optional_profiles", "required_capabilities", "optional_capabilities"]:
                    value = extension.get(field, [])
                    if not isinstance(value, list):
                        errors.append(f"manifest.protocol_extensions[{i}].{field} must be an array")
                    else:
                        for item_index, item in enumerate(value):
                            if not isinstance(item, str) or not item.strip():
                                errors.append(f"manifest.protocol_extensions[{i}].{field}[{item_index}] must be a non-empty string")

        delivery_readiness = manifest.get("delivery_readiness")
        if delivery_readiness is not None:
            if not isinstance(delivery_readiness, dict):
                errors.append("manifest.delivery_readiness must be an object")
            elif delivery_readiness.get("level") not in {"dev", "preview", "production"}:
                errors.append("manifest.delivery_readiness.level must be dev, preview, or production")

        protocol_certification = manifest.get("protocol_certification")
        if protocol_certification is not None:
            if not isinstance(protocol_certification, dict):
                errors.append("manifest.protocol_certification must be an object")
            else:
                if protocol_certification.get("status") not in {"certified"}:
                    errors.append("manifest.protocol_certification.status must be certified")
                for field in ["label", "protocol", "protocol_version"]:
                    if not isinstance(protocol_certification.get(field), str) or not protocol_certification.get(field).strip():
                        errors.append(f"manifest.protocol_certification.{field} is required")

        environment = manifest.get("environment", {})
        if not isinstance(environment, dict):
            errors.append("manifest.environment must be an object")
        else:
            os_list = environment.get("os", [])
            if os_list and not isinstance(os_list, list):
                errors.append("manifest.environment.os must be an array")
            requires = environment.get("requires", [])
            if not isinstance(requires, list):
                errors.append("manifest.environment.requires must be an array")
            else:
                for i, item in enumerate(requires):
                    if not isinstance(item, dict):
                        errors.append(f"manifest.environment.requires[{i}] must be an object")
                        continue
                    if not item.get("id"):
                        errors.append(f"manifest.environment.requires[{i}].id is required")
                    if item.get("type") not in {"command", "app_config"}:
                        errors.append(f"manifest.environment.requires[{i}].type must be command or app_config")
                    if item.get("type") == "command" and not item.get("command"):
                        errors.append(f"manifest.environment.requires[{i}].command is required for command check")
                    if item.get("type") == "app_config" and not item.get("key"):
                        errors.append(f"manifest.environment.requires[{i}].key is required for app_config check")

        if not isinstance(manifest.get("root_flow"), dict):
            errors.append("manifest.root_flow must be an object")
        else:
            root_entry = manifest["root_flow"].get("entry", "root.flow.json")
            if not (package_path / root_entry).is_file():
                errors.append(f"root_flow entry not found: {root_entry}")

        welcome = manifest.get("welcome") or {}
        if welcome:
            if not isinstance(welcome, dict):
                errors.append("manifest.welcome must be an object")
            elif welcome.get("type") == "markdown":
                entry = welcome.get("entry")
                if not entry:
                    errors.append("manifest.welcome.entry is required for markdown welcome")
                elif not (package_path / entry).is_file():
                    errors.append(f"welcome entry not found: {entry}")

        permissions = manifest.get("permissions", [])
        if not isinstance(permissions, list):
            errors.append("manifest.permissions must be an array")
        else:
            valid_levels = {"safe", "sensitive", "dangerous"}
            for i, perm in enumerate(permissions):
                if isinstance(perm, dict):
                    if not perm.get("id"):
                        errors.append(f"manifest.permissions[{i}].id is required")
                    level = perm.get("level")
                    if level and level not in valid_levels:
                        errors.append(f"manifest.permissions[{i}].level must be one of: safe, sensitive, dangerous")

        dependencies = manifest.get("dependencies", [])
        if not isinstance(dependencies, list):
            errors.append("manifest.dependencies must be an array")
        else:
            valid_dependency_types = {
                "system_package",
                "python_package",
                "node_package",
                "runtime_plugin",
                "browser_extension",
                "model",
                "local_asset",
            }
            valid_strategies = {"manual", "assisted", "automatic"}
            for i, dep in enumerate(dependencies):
                if not isinstance(dep, dict):
                    errors.append(f"manifest.dependencies[{i}] must be an object")
                    continue
                if not dep.get("id"):
                    errors.append(f"manifest.dependencies[{i}].id is required")
                if dep.get("type") not in valid_dependency_types:
                    errors.append(f"manifest.dependencies[{i}].type is invalid")
                install = dep.get("install", {})
                if install and not isinstance(install, dict):
                    errors.append(f"manifest.dependencies[{i}].install must be an object")
                elif isinstance(install, dict):
                    strategy = install.get("strategy") or dep.get("strategy")
                    if strategy and strategy not in valid_strategies:
                        errors.append(f"manifest.dependencies[{i}].install.strategy must be manual, assisted, or automatic")

        if not isinstance(manifest.get("inputs", []), list):
            errors.append("manifest.inputs must be an array")
        if not isinstance(manifest.get("outputs", []), list):
            errors.append("manifest.outputs must be an array")

        self._validate_llm_recipe(manifest.get("llm_recipe"), errors)
        resource_roles = self._validate_resource_requirements(manifest.get("resource_requirements"), errors)

        mcp_tools = manifest.get("mcp_tools", [])
        if not isinstance(mcp_tools, list):
            errors.append("manifest.mcp_tools must be an array")
        else:
            for i, tool in enumerate(mcp_tools):
                if not isinstance(tool, dict):
                    errors.append(f"manifest.mcp_tools[{i}] must be an object")
                    continue
                if not tool.get("id"):
                    errors.append(f"manifest.mcp_tools[{i}].id is required")
                if tool.get("type") not in {None, "builtin", "mcp", "remote", "plugin"}:
                    errors.append(f"manifest.mcp_tools[{i}].type must be builtin, mcp, remote, or plugin")
                if not tool.get("server"):
                    errors.append(f"manifest.mcp_tools[{i}].server is required")
                if not tool.get("tool"):
                    errors.append(f"manifest.mcp_tools[{i}].tool is required")
                if "required" in tool and not isinstance(tool.get("required"), bool):
                    errors.append(f"manifest.mcp_tools[{i}].required must be a boolean")
                if is_v06 or is_v07:
                    self._reject_llm_recipe_local_fields(tool, f"manifest.mcp_tools[{i}]", errors)
                    tool_type = tool.get("type") or "builtin"
                    resource_role = str(tool.get("resource_role") or "").strip()
                    if tool_type in {"mcp", "remote", "plugin"} and not resource_role:
                        errors.append(f"manifest.mcp_tools[{i}].resource_role is required for external tools")
                    elif resource_role and resource_role not in resource_roles:
                        errors.append(f"manifest.mcp_tools[{i}].resource_role must reference resource_requirements")
                contract = tool.get("contract")
                if contract is not None:
                    if not isinstance(contract, dict):
                        errors.append(f"manifest.mcp_tools[{i}].contract must be an object")
                    else:
                        if "timeout_ms" in contract and not isinstance(contract.get("timeout_ms"), int):
                            errors.append(f"manifest.mcp_tools[{i}].contract.timeout_ms must be an integer")
                        if "idempotent" in contract and not isinstance(contract.get("idempotent"), bool):
                            errors.append(f"manifest.mcp_tools[{i}].contract.idempotent must be a boolean")
                        retry_policy = contract.get("retry_policy")
                        if retry_policy is not None and not isinstance(retry_policy, dict):
                            errors.append(f"manifest.mcp_tools[{i}].contract.retry_policy must be an object")

        portable_dlc = manifest.get("portable_dlc")
        if portable_dlc is not None:
            if not isinstance(portable_dlc, dict):
                errors.append("manifest.portable_dlc must be an object")
            elif not (is_v06 or is_v07):
                errors.append("manifest.portable_dlc activation requires a supported CF-FARP version")
            else:
                try:
                    load_portable_dlc_descriptor(package_path, manifest)
                except PortableDlcValidationError as exc:
                    errors.append(str(exc))

        if is_v07:
            asset_registry = manifest.get("asset_registry")
            if not isinstance(asset_registry, str) or not asset_registry.strip():
                errors.append("CF-FARP@0.7 requires manifest.asset_registry")
            else:
                try:
                    bundle = load_asset_bundle(package_path, manifest)
                    root_entry = str((manifest.get("root_flow") or {}).get("entry") or "root.flow.json")
                    root_path = package_path / root_entry
                    root_flow = json.loads(root_path.read_text(encoding="utf-8")) if root_path.is_file() else {}
                    for finding in validate_interaction_nodes(root_flow, bundle):
                        if finding.get("severity") == "blocker":
                            errors.append(f"{finding.get('code')}: {finding.get('node')}: {finding.get('message')}")
                except (CartridgeAssetError, json.JSONDecodeError, UnicodeError) as exc:
                    code = getattr(exc, "code", "CARTRIDGE_ASSET_INVALID")
                    errors.append(f"{code}: {exc}")

        if errors:
            raise ManifestValidationError("; ".join(errors))
        return manifest

    def _validate_resource_requirements(self, requirements, errors: list[str]) -> set[str]:
        if requirements is None:
            return set()
        if not isinstance(requirements, list):
            errors.append("manifest.resource_requirements must be an array")
            return set()
        roles = set()
        allowed_kinds = {"mcp", "remote_api", "plugin", "local_path", "web", "structured"}
        for index, requirement in enumerate(requirements):
            path = f"manifest.resource_requirements[{index}]"
            if not isinstance(requirement, dict):
                errors.append(f"{path} must be an object")
                continue
            role = str(requirement.get("role") or "").strip()
            if not role:
                errors.append(f"{path}.role is required")
            elif role in roles:
                errors.append(f"{path}.role must be unique")
            else:
                roles.add(role)
            kinds = requirement.get("kinds")
            if not isinstance(kinds, list) or not kinds:
                errors.append(f"{path}.kinds must be a non-empty array")
            elif any(str(kind or "").strip() not in allowed_kinds for kind in kinds):
                errors.append(f"{path}.kinds contains an unsupported resource kind")
            capabilities = requirement.get("capabilities")
            if capabilities is not None and not isinstance(capabilities, list):
                errors.append(f"{path}.capabilities must be an array")
            constraints = requirement.get("constraints")
            if constraints is not None and not isinstance(constraints, dict):
                errors.append(f"{path}.constraints must be an object")
            if "required" in requirement and not isinstance(requirement.get("required"), bool):
                errors.append(f"{path}.required must be a boolean")
            self._reject_llm_recipe_local_fields(requirement, path, errors)
        return roles

    def _validate_llm_recipe(self, recipe, errors: list[str]):
        if recipe is None:
            return
        if not isinstance(recipe, dict):
            errors.append("manifest.llm_recipe must be an object")
            return
        if recipe.get("schema") != "cartridgeflow.llm_recipe.v1":
            errors.append("manifest.llm_recipe.schema must be cartridgeflow.llm_recipe.v1")
        roles = recipe.get("roles")
        if not isinstance(roles, list):
            errors.append("manifest.llm_recipe.roles must be an array")
            roles = []

        seen_ids = set()
        for index, role in enumerate(roles):
            path = f"manifest.llm_recipe.roles[{index}]"
            if not isinstance(role, dict):
                errors.append(f"{path} must be an object")
                continue
            for field in ["id", "label", "capability", "api_type", "wire_api", "model"]:
                if not isinstance(role.get(field), str) or not role.get(field).strip():
                    errors.append(f"{path}.{field} is required")
            role_id = role.get("id")
            if isinstance(role_id, str) and role_id.strip():
                if role_id in seen_ids:
                    errors.append(f"{path}.id must be unique")
                seen_ids.add(role_id)
            if "required" in role and not isinstance(role.get("required"), bool):
                errors.append(f"{path}.required must be a boolean")

        self._reject_llm_recipe_local_fields(recipe, "manifest.llm_recipe", errors)

    def _reject_llm_recipe_local_fields(self, value, path: str, errors: list[str]):
        if isinstance(value, dict):
            for key, item in value.items():
                item_path = f"{path}.{key}"
                if str(key).lower() in self.LLM_RECIPE_LOCAL_FIELDS:
                    errors.append(f"{item_path} is local-only and must not be stored in a cartridge")
                self._reject_llm_recipe_local_fields(item, item_path, errors)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._reject_llm_recipe_local_fields(item, f"{path}[{index}]", errors)
