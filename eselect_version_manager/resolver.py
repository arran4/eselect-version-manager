"""Precedence-based toolchain version resolver and explanation engine."""

import os
from typing import Dict, List, Optional, Tuple

from .config import (
    get_system_config_path,
    get_user_config_path,
    get_shims_dir,
    parse_declarative_config,
    tool_key,
)
from .errors import (
    NoMatchingVersionError,
    RecursionError,
    UnknownToolError,
    VersionManagerError,
    ExitCode,
)
from .models import (
    ResolutionResult,
    ResolutionStep,
    Scope,
    ToolSelection,
)
from .portage_backend import get_installed_packages, match_packages
from .project import (
    find_project_hierarchy,
    read_private_project_config,
    canonicalize_path,
)
from .providers.registry import ProviderRegistry, get_default_registry


def find_system_executable(command: str) -> Optional[str]:
    """Find real system executable in PATH, strictly excluding the user-local shims directory."""
    shims_dir = os.path.realpath(get_shims_dir())
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)

    for directory in path_dirs:
        if not directory:
            continue
        real_dir = os.path.realpath(directory)
        if real_dir == shims_dir:
            continue
        candidate = os.path.join(directory, command)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)

    # Also check standard Gentoo system directories
    for fallback_dir in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        candidate = os.path.join(fallback_dir, command)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


class Resolver:
    """Core resolver implementing Gentoo-native toolchain precedence."""

    def __init__(self, registry: Optional[ProviderRegistry] = None, eroot: Optional[str] = None):
        self.registry = registry or get_default_registry()
        self.eroot = eroot or os.environ.get("EROOT") or "/"

    def resolve(
        self,
        tool_or_command: str,
        current_dir: Optional[str] = None,
        overrides: Optional[Dict[str, str]] = None,
        command_override: Optional[str] = None,
    ) -> ResolutionResult:
        """
        Resolve a tool or command name to an executable and environment.
        Follows strict precedence:
          Explicit invocation override
          -> Nearest project selection (private user-project overrides .eselect.conf)
          -> Parent project selection (per-tool inheritance)
          -> User-wide default (~/.config/eselect/version-manager.conf)
          -> System-wide default (/etc/eselect/version-manager.conf)
          -> Existing Gentoo-selected/system executable
        """
        provider = self.registry.get_provider(tool_or_command)
        tool_name = provider.name
        command = command_override or (
            tool_or_command if tool_or_command in provider.commands else provider.commands[0]
        )

        # Check recursion guard
        active_tool = os.environ.get("_ESELECT_VM_ACTIVE_TOOL")
        if active_tool == command:
            raise RecursionError(command, details={"tool": tool_name})

        # Check bypass mechanism
        if os.environ.get("VM_BYPASS") == "1" or os.environ.get("ESELECT_VM_BYPASS") == "1":
            sys_exec = find_system_executable(command)
            if not sys_exec:
                raise NoMatchingVersionError(
                    tool=tool_name,
                    requested="system (bypass)",
                    provider=provider.package_atom,
                    details={"reason": f"system executable '{command}' not found in PATH"}
                )
            return ResolutionResult(
                tool=tool_name,
                command=command,
                requested_constraint="system",
                selected_scope=Scope.SYSTEM_FALLBACK,
                source_file=None,
                project_root=None,
                provider_name=provider.name,
                provider_atom=provider.package_atom,
                package=None,
                executable_path=sys_exec,
                env_vars={},
                steps=[ResolutionStep(Scope.SYSTEM_FALLBACK, "PATH (bypass requested)", tool_name, "system", True)],
                is_system_fallback=True,
            )

        steps: List[ResolutionStep] = []
        cwd = canonicalize_path(current_dir or os.getcwd())
        t_key = tool_key(tool_name)

        selected_val: Optional[str] = None
        selected_scope: Optional[Scope] = None
        selected_source: Optional[str] = None
        effective_project_root: Optional[str] = None

        # 1. Check explicit command invocation override
        env_override_key = f"VM_OVERRIDE_{t_key[3:]}"
        cli_override = (overrides or {}).get(tool_name) or os.environ.get(env_override_key)
        if cli_override:
            selected_val = cli_override
            selected_scope = Scope.INVOCATION_OVERRIDE
            selected_source = "command override" if overrides and tool_name in overrides else f"${env_override_key}"
            steps.append(ResolutionStep(selected_scope, selected_source, tool_name, selected_val, True))

        # 2. Project hierarchy (nearest project wins; parent projects provide inheritance per tool)
        if not selected_val:
            hierarchy = find_project_hierarchy(cwd)
            for idx, proj in enumerate(hierarchy):
                p_root = proj["project_root"]
                is_nearest = (idx == 0)

                # Check private user-project configuration first
                if proj["has_private_conf"]:
                    priv_conf = read_private_project_config(p_root)
                    if priv_conf and t_key in priv_conf:
                        selected_val = priv_conf[t_key]
                        selected_scope = Scope.USER_PROJECT if is_nearest else Scope.PARENT_PROJECT
                        selected_source = proj["private_conf_path"]
                        effective_project_root = p_root
                        steps.append(ResolutionStep(
                            selected_scope,
                            selected_source,
                            tool_name,
                            selected_val,
                            True,
                            details=f"Project root: {p_root}"
                        ))
                        break
                    else:
                        steps.append(ResolutionStep(
                            Scope.USER_PROJECT if is_nearest else Scope.PARENT_PROJECT,
                            proj["private_conf_path"],
                            tool_name,
                            None,
                            False,
                            details="Tool not specified in private project config"
                        ))

                # Check .eselect.conf next
                if proj["has_file_conf"]:
                    file_conf = parse_declarative_config(proj["file_conf_path"])
                    if t_key in file_conf:
                        selected_val = file_conf[t_key]
                        selected_scope = Scope.PROJECT_FILE if is_nearest else Scope.PARENT_PROJECT
                        selected_source = proj["file_conf_path"]
                        effective_project_root = p_root
                        steps.append(ResolutionStep(
                            selected_scope,
                            selected_source,
                            tool_name,
                            selected_val,
                            True,
                            details=f"Project root: {p_root}"
                        ))
                        break
                    else:
                        steps.append(ResolutionStep(
                            Scope.PROJECT_FILE if is_nearest else Scope.PARENT_PROJECT,
                            proj["file_conf_path"],
                            tool_name,
                            None,
                            False,
                            details="Tool not specified in .eselect.conf"
                        ))

        # 3. User default: ~/.config/eselect/version-manager.conf
        if not selected_val:
            user_conf_path = get_user_config_path()
            if os.path.isfile(user_conf_path):
                user_conf = parse_declarative_config(user_conf_path)
                if t_key in user_conf:
                    selected_val = user_conf[t_key]
                    selected_scope = Scope.USER_DEFAULT
                    selected_source = user_conf_path
                    steps.append(ResolutionStep(selected_scope, selected_source, tool_name, selected_val, True))
                else:
                    steps.append(ResolutionStep(Scope.USER_DEFAULT, user_conf_path, tool_name, None, False))
            else:
                steps.append(ResolutionStep(Scope.USER_DEFAULT, user_conf_path, tool_name, None, False, "File does not exist"))

        # 4. System default: /etc/eselect/version-manager.conf
        if not selected_val:
            sys_conf_path = get_system_config_path(self.eroot)
            if os.path.isfile(sys_conf_path):
                sys_conf = parse_declarative_config(sys_conf_path)
                if t_key in sys_conf:
                    selected_val = sys_conf[t_key]
                    selected_scope = Scope.SYSTEM_DEFAULT
                    selected_source = sys_conf_path
                    steps.append(ResolutionStep(selected_scope, selected_source, tool_name, selected_val, True))
                else:
                    steps.append(ResolutionStep(Scope.SYSTEM_DEFAULT, sys_conf_path, tool_name, None, False))
            else:
                steps.append(ResolutionStep(Scope.SYSTEM_DEFAULT, sys_conf_path, tool_name, None, False, "File does not exist"))

        # 5. Fallback to existing Gentoo system executable
        if not selected_val:
            selected_val = "system"
            selected_scope = Scope.SYSTEM_FALLBACK
            selected_source = "system PATH"
            steps.append(ResolutionStep(selected_scope, selected_source, tool_name, "system", True, "Default fallback"))

        # Execute resolution of selected_val
        return self._resolve_target(
            provider=provider,
            command=command,
            raw_value=selected_val,
            scope=selected_scope,
            source_file=selected_source,
            project_root=effective_project_root or cwd,
            steps=steps,
        )

    def _resolve_target(
        self,
        provider,
        command: str,
        raw_value: str,
        scope: Scope,
        source_file: Optional[str],
        project_root: str,
        steps: List[ResolutionStep],
    ) -> ResolutionResult:
        tool_name = provider.name
        val = raw_value.strip()

        # Handle 'from-file' native version discovery
        if val == "from-file":
            if not provider.supports_native_file:
                raise VersionManagerError(
                    f"tool '{tool_name}' does not support 'from-file' native version detection",
                    exit_code=ExitCode.UNSUPPORTED_VERSION_FILE,
                    details={"tool": tool_name, "provider": provider.package_atom}
                )

            installed_pkgs = get_installed_packages(provider.package_atom, eroot=self.eroot)
            if hasattr(provider, "resolve_native_package"):
                best_pkg, effective_desc = provider.resolve_native_package(project_root, installed_pkgs)
                steps.append(ResolutionStep(
                    scope,
                    f"from-file ({project_root})",
                    tool_name,
                    effective_desc,
                    True,
                    details=f"Derived from native project configuration in {project_root}"
                ))
                exec_path = provider.find_executable(best_pkg, command)
                env_vars = provider.get_environment(best_pkg, exec_path)
                return ResolutionResult(
                    tool=tool_name,
                    command=command,
                    requested_constraint=raw_value,
                    selected_scope=scope,
                    source_file=source_file,
                    project_root=project_root,
                    provider_name=provider.name,
                    provider_atom=provider.package_atom,
                    package=best_pkg,
                    executable_path=exec_path,
                    env_vars=env_vars,
                    steps=steps,
                    is_system_fallback=False,
                )
            else:
                effective_constraint = provider.parse_native_version_file(project_root)
                steps.append(ResolutionStep(
                    scope,
                    f"from-file ({project_root})",
                    tool_name,
                    effective_constraint,
                    True,
                    details=f"Derived from native project configuration in {project_root}"
                ))
                constraint_to_match = effective_constraint
        elif val == "system":
            # Delegate to existing Gentoo default executable
            sys_exec = find_system_executable(command)
            if not sys_exec:
                raise NoMatchingVersionError(
                    tool=tool_name,
                    requested="system",
                    provider=provider.package_atom,
                    details={
                        "source": source_file,
                        "project": project_root,
                        "reason": f"system default executable '{command}' not found in PATH"
                    }
                )
            return ResolutionResult(
                tool=tool_name,
                command=command,
                requested_constraint="system",
                selected_scope=scope,
                source_file=source_file,
                project_root=project_root,
                provider_name=provider.name,
                provider_atom=provider.package_atom,
                package=None,
                executable_path=sys_exec,
                env_vars={},
                steps=steps,
                is_system_fallback=True,
            )
        else:
            constraint_to_match = val

        # Query installed Portage packages
        installed_pkgs = get_installed_packages(provider.package_atom, eroot=self.eroot)
        matched_pkgs = match_packages(installed_pkgs, provider.package_atom, constraint_to_match)

        if not matched_pkgs:
            installed_strs = [f"{p.version} (slot {p.slot})" for p in installed_pkgs]
            raise NoMatchingVersionError(
                tool=tool_name,
                requested=constraint_to_match,
                provider=provider.package_atom,
                installed=installed_strs,
                details={
                    "source": source_file,
                    "project": project_root,
                    "scope": scope.display_name(),
                }
            )

        # Best matching installed package (highest version)
        best_pkg = matched_pkgs[-1]

        # Locate executable within package
        exec_path = provider.find_executable(best_pkg, command)

        # Get environment variables
        env_vars = provider.get_environment(best_pkg, exec_path)

        return ResolutionResult(
            tool=tool_name,
            command=command,
            requested_constraint=raw_value,
            selected_scope=scope,
            source_file=source_file,
            project_root=project_root,
            provider_name=provider.name,
            provider_atom=provider.package_atom,
            package=best_pkg,
            executable_path=exec_path,
            env_vars=env_vars,
            steps=steps,
            is_system_fallback=False,
        )
