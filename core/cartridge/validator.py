from pathlib import Path


class ManifestValidationError(ValueError):
    pass


class ManifestValidator:
    REQUIRED_STRING_FIELDS = ["schema_version", "id", "name", "version", "kind", "category"]

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
                if tool.get("type") not in {None, "builtin", "mcp"}:
                    errors.append(f"manifest.mcp_tools[{i}].type must be builtin or mcp")
                if not tool.get("server"):
                    errors.append(f"manifest.mcp_tools[{i}].server is required")
                if not tool.get("tool"):
                    errors.append(f"manifest.mcp_tools[{i}].tool is required")
                if "required" in tool and not isinstance(tool.get("required"), bool):
                    errors.append(f"manifest.mcp_tools[{i}].required must be a boolean")
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

        if errors:
            raise ManifestValidationError("; ".join(errors))
        return manifest
