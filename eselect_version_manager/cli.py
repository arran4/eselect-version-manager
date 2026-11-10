"""Command-line interface and dispatcher for eselect-version-manager."""

import argparse
import os
import sys
from typing import List, Optional

from .config import (
    get_system_config_path,
    get_user_config_path,
    parse_declarative_config,
    update_config_file,
    validate_version_constraint,
    tool_key,
    tool_from_key,
)
from .conversion import convert_to_file, convert_to_user
from .doctor import run_doctor
from .errors import (
    ExitCode,
    UnknownToolError,
    VersionManagerError,
)
from .models import Scope
from .portage_backend import get_installed_packages
from .project import (
    canonicalize_path,
    get_project_file_path,
    read_private_project_config,
    save_private_project_config,
    rebind_project,
)
from .providers.registry import get_default_registry
from .resolver import Resolver, find_system_executable
from .shims import ShimManager, is_shim_disabled


def main(args: Optional[List[str]] = None) -> int:
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="eselect-version-manager",
        description="Gentoo-native project-aware toolchain version manager",
    )
    parser.add_argument("--eroot", default=None, help="Gentoo EROOT prefix")

    subparsers = parser.add_subparsers(dest="subcommand", metavar="<action>")

    # dispatch
    p_dispatch = subparsers.add_parser("dispatch", help="Dispatch command through shim")
    p_dispatch.add_argument("command", help="Command name to execute")
    p_dispatch.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass through")

    # list
    p_list = subparsers.add_parser("list", help="List registered tools or installed versions")
    p_list.add_argument("tool", nargs="?", default=None, help="Tool name (e.g. go)")

    # show
    p_show = subparsers.add_parser("show", help="Show active version for a tool")
    p_show.add_argument("tool", nargs="?", default=None, help="Tool name (e.g. go)")

    # resolve / explain
    p_resolve = subparsers.add_parser("resolve", help="Show detailed resolution trace")
    p_resolve.add_argument("tool", help="Tool or command name")
    p_resolve.add_argument("--explain", action="store_true", help="Verbose explanation")

    p_explain = subparsers.add_parser("explain", help="Show detailed resolution trace (alias)")
    p_explain.add_argument("tool", help="Tool or command name")

    # set
    p_set = subparsers.add_parser("set", help="Set tool version constraint")
    p_set.add_argument("tool", help="Tool name (e.g. go)")
    p_set.add_argument("version", help="Version constraint (e.g. 1.26, >=1.26, latest, from-file, system)")
    p_set.add_argument("--system", "--global", action="store_true", dest="is_system", help="Set in /etc/eselect/version-manager.conf")
    p_set.add_argument("--user", action="store_true", dest="is_user", help="Set in ~/.config/eselect/version-manager.conf")
    p_set.add_argument("--project", action="store_true", dest="is_project", help="Set in project scope")
    p_set.add_argument("--user-project", action="store_true", dest="is_user_project", help="Set in private user-project configuration")
    p_set.add_argument("--file", action="store_true", dest="is_file", help="Write to .eselect.conf (converts private selections)")
    p_set.add_argument("--force", action="store_true", help="Force overwrite on conversion conflict")

    # unset
    p_unset = subparsers.add_parser("unset", help="Unset tool version constraint")
    p_unset.add_argument("tool", help="Tool name")
    p_unset.add_argument("--system", "--global", action="store_true", dest="is_system")
    p_unset.add_argument("--user", action="store_true", dest="is_user")
    p_unset.add_argument("--project", action="store_true", dest="is_project")
    p_unset.add_argument("--user-project", action="store_true", dest="is_user_project")
    p_unset.add_argument("--file", action="store_true", dest="is_file")

    # convert
    p_convert = subparsers.add_parser("convert", help="Convert project configuration between private and .eselect.conf")
    p_convert.add_argument("--to-file", action="store_true", dest="to_file", help="Convert private project config to .eselect.conf")
    p_convert.add_argument("--to-user", action="store_true", dest="to_user", help="Convert .eselect.conf to private user config")
    p_convert.add_argument("--force", action="store_true", help="Force overwrite on conflicts")
    p_convert.add_argument("path", nargs="?", default=".", help="Project directory (default: current directory)")

    # rebind
    p_rebind = subparsers.add_parser("rebind", help="Rebind moved project private configuration")
    p_rebind.add_argument("old_path", help="Old project root directory")
    p_rebind.add_argument("new_path", nargs="?", default=".", help="New project root directory (default: current directory)")

    # shims
    p_shims = subparsers.add_parser("shims", help="Manage user-local shims")
    shims_sub = p_shims.add_subparsers(dest="shim_action", metavar="<shim-action>")

    p_s_install = shims_sub.add_parser("install", help="Install executable shims")
    p_s_install.add_argument("tools", nargs="*", help="Tools to install (default: all)")

    p_s_enable = shims_sub.add_parser("enable", help="Enable shims")
    p_s_enable.add_argument("tools", nargs="*", help="Tools to enable (default: all)")

    p_s_disable = shims_sub.add_parser("disable", help="Disable shims")
    p_s_disable.add_argument("tools", nargs="*", help="Tools to disable")

    p_s_uninstall = shims_sub.add_parser("uninstall", help="Uninstall shims")
    p_s_uninstall.add_argument("tools", nargs="*", help="Tools to uninstall (default: all)")

    p_s_list = shims_sub.add_parser("list", help="List installed shims")
    p_s_env = shims_sub.add_parser("env", help="Show PATH activation snippet")

    # exec
    p_exec = subparsers.add_parser("exec", help="Execute command with tool override")
    p_exec.add_argument("--tool", action="append", default=[], help="Tool override in format TOOL=VERSION")
    p_exec.add_argument("cmd_and_args", nargs=argparse.REMAINDER, help="Command and arguments to run")

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Verify system configuration and diagnostics")

    parsed = parser.parse_args(args)
    if not parsed.subcommand:
        parser.print_help()
        return ExitCode.INVALID_USAGE

    try:
        if parsed.subcommand == "dispatch":
            return cmd_dispatch(parsed.command, parsed.args, eroot=parsed.eroot)
        elif parsed.subcommand == "list":
            return cmd_list(parsed.tool, eroot=parsed.eroot)
        elif parsed.subcommand == "show":
            return cmd_show(parsed.tool, eroot=parsed.eroot)
        elif parsed.subcommand in ("resolve", "explain"):
            return cmd_resolve(parsed.tool, eroot=parsed.eroot)
        elif parsed.subcommand == "set":
            return cmd_set(parsed)
        elif parsed.subcommand == "unset":
            return cmd_unset(parsed)
        elif parsed.subcommand == "convert":
            return cmd_convert(parsed)
        elif parsed.subcommand == "rebind":
            return cmd_rebind(parsed)
        elif parsed.subcommand == "shims":
            return cmd_shims(parsed)
        elif parsed.subcommand == "exec":
            return cmd_exec(parsed)
        elif parsed.subcommand == "doctor":
            return cmd_doctor(parsed)
    except VersionManagerError as e:
        print(e.format_diagnostic(), file=sys.stderr)
        return int(e.exit_code)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"eselect-version-manager: unexpected internal error: {e}", file=sys.stderr)
        return ExitCode.GENERAL_ERROR

    return ExitCode.SUCCESS


def cmd_dispatch(command: str, args: List[str], eroot: Optional[str] = None) -> int:
    # Check if disabled
    if is_shim_disabled(command):
        sys_exec = find_system_executable(command)
        if not sys_exec:
            print(f"eselect-version-manager: shim '{command}' is disabled and no system executable found in PATH", file=sys.stderr)
            return ExitCode.NO_MATCHING_VERSION
        os.execv(sys_exec, [command] + args)

    resolver = Resolver(eroot=eroot)
    res = resolver.resolve(command)

    # Prepare execution environment
    env = dict(os.environ)
    env["_ESELECT_VM_ACTIVE_TOOL"] = command
    env.update(res.env_vars)

    # Execute target binary directly
    os.execvpe(res.executable_path, [command] + args, env)


def cmd_list(tool: Optional[str], eroot: Optional[str] = None) -> int:
    registry = get_default_registry()
    if tool is None:
        print("Available toolchains:")
        for t in registry.list_tools():
            provider = registry.get_provider(t)
            print(f"  {t:<14} -> {provider.package_atom} (commands: {', '.join(provider.commands)})")
        return ExitCode.SUCCESS

    provider = registry.get_provider(tool)
    pkgs = get_installed_packages(provider.package_atom, eroot=eroot)
    if not pkgs:
        print(f"No installed versions found for {provider.package_atom}")
        return ExitCode.SUCCESS

    # Try resolving current active version to place an asterisk
    active_cpv = None
    try:
        resolver = Resolver(eroot=eroot)
        res = resolver.resolve(tool)
        if res.package:
            active_cpv = res.package.cpv
    except Exception:
        pass

    print(f"Installed versions for {provider.package_atom}:")
    for idx, p in enumerate(pkgs, 1):
        marker = "* " if p.cpv == active_cpv else "  "
        ver_display = f"{p.version}-{p.revision}" if p.revision and p.revision != "r0" else p.version
        slot_info = f" (slot {p.slot})" if p.slot != "0" else ""
        print(f"  [{idx}] {marker}{ver_display}{slot_info}")

    return ExitCode.SUCCESS


def cmd_show(tool: Optional[str], eroot: Optional[str] = None) -> int:
    registry = get_default_registry()
    tools = [tool] if tool else registry.list_tools()
    resolver = Resolver(eroot=eroot)

    for t in tools:
        try:
            res = resolver.resolve(t)
            if res.is_system_fallback:
                ver_display = "system (default fallback)"
            elif res.package:
                ver_display = f"{res.package.version} (slot {res.package.slot})"
            else:
                ver_display = res.requested_constraint
            print(f"{t}: {ver_display} [{res.selected_scope.display_name()}]")
        except VersionManagerError as e:
            print(f"{t}: cannot resolve ({e.message})")

    return ExitCode.SUCCESS


def cmd_resolve(tool: str, eroot: Optional[str] = None) -> int:
    resolver = Resolver(eroot=eroot)
    res = resolver.resolve(tool)

    print(f"Resolution report for '{tool}':")
    print(f"  Tool:         {res.tool}")
    print(f"  Command:      {res.command}")
    print(f"  Provider:     {res.provider_atom}")
    print(f"  Scope:        {res.selected_scope.display_name()}")
    print(f"  Source:       {res.source_file or '(system)'}")
    print(f"  Project root: {res.project_root or '(none)'}")
    print(f"  Constraint:   {res.requested_constraint}")

    if res.package:
        print(f"  Package:      {res.package.cpv} (slot {res.package.slot})")
    print(f"  Executable:   {res.executable_path}")

    if res.env_vars:
        print("  Environment:")
        for k, v in sorted(res.env_vars.items()):
            print(f"    {k}={v}")

    print("\nPrecedence evaluation chain:")
    for step in res.steps:
        status = "MATCH" if step.matched else "skip"
        val_str = f"'{step.raw_value}'" if step.raw_value else "-"
        detail = f" ({step.details})" if step.details else ""
        print(f"  [{status:<5}] {step.scope.display_name():<25} from {step.source_location}: {val_str}{detail}")

    return ExitCode.SUCCESS


def cmd_set(parsed) -> int:
    tool = parsed.tool.lower()
    version = parsed.version.strip()
    validate_version_constraint(tool, version)
    cwd = canonicalize_path(os.getcwd())
    key = tool_key(tool)

    # Determine target scope
    if parsed.is_system:
        # System wide
        sys_conf = get_system_config_path(parsed.eroot)
        update_config_file(sys_conf, {key: version}, header_comment="eselect-version-manager system defaults")
        print(f"Set system-wide default {key}=\"{version}\" in {sys_conf}")
        return ExitCode.SUCCESS

    if parsed.is_user:
        # User wide
        user_conf = get_user_config_path()
        update_config_file(user_conf, {key: version}, header_comment="eselect-version-manager user defaults")
        print(f"Set user default {key}=\"{version}\" in {user_conf}")
        return ExitCode.SUCCESS

    if parsed.is_file or (parsed.is_project and parsed.is_file):
        # Convert existing private selections and write to .eselect.conf
        res = convert_to_file(cwd, force=parsed.force, additional_updates={key: version})
        print(f"Set {key}=\"{version}\" in project file {res['file_path']}")
        if res.get("private_removed"):
            print("  (Migrated and cleaned up existing private project selections)")
        return ExitCode.SUCCESS

    # Default to private user-project configuration
    conf_path = save_private_project_config(cwd, {key: version})
    print(f"Set private project selection {key}=\"{version}\" for {cwd}")
    print(f"  (Saved in {conf_path})")
    return ExitCode.SUCCESS


def cmd_unset(parsed) -> int:
    tool = parsed.tool.lower()
    cwd = canonicalize_path(os.getcwd())
    key = tool_key(tool)

    if parsed.is_system:
        sys_conf = get_system_config_path(parsed.eroot)
        update_config_file(sys_conf, {key: None})
        print(f"Unset {key} in system defaults")
        return ExitCode.SUCCESS

    if parsed.is_user:
        user_conf = get_user_config_path()
        update_config_file(user_conf, {key: None})
        print(f"Unset {key} in user defaults")
        return ExitCode.SUCCESS

    if parsed.is_file:
        file_path = get_project_file_path(cwd)
        if os.path.exists(file_path):
            update_config_file(file_path, {key: None})
            print(f"Unset {key} in {file_path}")
        return ExitCode.SUCCESS

    # Default to private user-project configuration
    save_private_project_config(cwd, {key: None})
    print(f"Unset private project selection {key} for {cwd}")
    return ExitCode.SUCCESS


def cmd_convert(parsed) -> int:
    target_path = canonicalize_path(parsed.path)
    if parsed.to_file:
        res = convert_to_file(target_path, force=parsed.force)
        print(f"Successfully converted project selections to {res['file_path']}:")
        for k, v in res["converted"].items():
            print(f"  {k}=\"{v}\"")
        return ExitCode.SUCCESS
    elif parsed.to_user:
        res = convert_to_user(target_path, force=parsed.force)
        print(f"Successfully converted project selections to private user storage for {target_path}:")
        for k, v in res["converted"].items():
            print(f"  {k}=\"{v}\"")
        return ExitCode.SUCCESS
    else:
        print("eselect-version-manager: must specify --to-file or --to-user", file=sys.stderr)
        return ExitCode.INVALID_USAGE


def cmd_rebind(parsed) -> int:
    old_p, new_p = rebind_project(parsed.old_path, parsed.new_path)
    print(f"Successfully rebound project:")
    print(f"  Old config: {old_p}")
    print(f"  New config: {new_p}")
    return ExitCode.SUCCESS


def cmd_shims(parsed) -> int:
    mgr = ShimManager()
    action = parsed.shim_action
    if not action or action == "list":
        shims = mgr.list_shims()
        if not shims:
            print("No user-local shims installed.")
            print(f"Install shims with: eselect version-manager shims install [tool]")
            return ExitCode.SUCCESS
        print(f"{'Command':<16} {'Tool':<12} {'Status':<10} {'Provider':<32} {'Path'}")
        print("-" * 80)
        for s in shims:
            print(f"{s['command']:<16} {s['tool']:<12} {s['status']:<10} {s['provider']:<32} {s['path']}")
        return ExitCode.SUCCESS

    registry = get_default_registry()
    tools = parsed.tools or registry.list_tools()

    if action == "install":
        installed = mgr.install(tools)
        print(f"Installed {len(installed)} shim(s): {', '.join(installed)}")
        print(f"Shims directory: {mgr.shims_dir}")
        print(f"Ensure shims are in PATH: {mgr.get_activation_env()}")
    elif action == "enable":
        enabled = mgr.enable(tools)
        print(f"Enabled {len(enabled)} shim(s): {', '.join(enabled)}")
    elif action == "disable":
        if not parsed.tools:
            print("eselect-version-manager: specify tools or commands to disable", file=sys.stderr)
            return ExitCode.INVALID_USAGE
        disabled = mgr.disable(parsed.tools)
        print(f"Disabled {len(disabled)} shim(s): {', '.join(disabled)}")
    elif action == "uninstall":
        uninstalled = mgr.uninstall(tools)
        print(f"Uninstalled {len(uninstalled)} shim(s): {', '.join(uninstalled)}")
    elif action == "env":
        print(mgr.get_activation_env())
    else:
        print(f"eselect-version-manager: unknown shims action '{action}'", file=sys.stderr)
        return ExitCode.INVALID_USAGE

    return ExitCode.SUCCESS


def cmd_exec(parsed) -> int:
    args = parsed.cmd_and_args
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        print("eselect-version-manager: no command specified to execute", file=sys.stderr)
        return ExitCode.INVALID_USAGE

    overrides = {}
    for item in parsed.tool:
        if "=" in item:
            t, v = item.split("=", 1)
            overrides[t.lower()] = v

    command = args[0]
    cmd_args = args[1:]

    resolver = Resolver()
    # Check if command belongs to a tool
    provider = resolver.registry.find_provider_for_command(command)
    if provider:
        res = resolver.resolve(command, overrides=overrides)
        env = dict(os.environ)
        env["_ESELECT_VM_ACTIVE_TOOL"] = command
        env.update(res.env_vars)
        os.execvpe(res.executable_path, args, env)
    else:
        # Not a managed tool command, execute in PATH directly
        os.execvp(command, args)


def cmd_doctor(parsed) -> int:
    all_passed, lines = run_doctor(eroot=parsed.eroot)
    for line in lines:
        print(line)
    return ExitCode.SUCCESS if all_passed else ExitCode.GENERAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
