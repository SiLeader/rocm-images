"""Command-line entry point for rocm-images."""

import argparse

from . import build, generate_dockerfile, tree


def main(argv=None):
    parser = argparse.ArgumentParser(description="ROCm image tools")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, module in (("build", build), ("tree", tree), ("generate-dockerfile", generate_dockerfile)):
        command = commands.add_parser(name, help=module.__doc__, parents=[module.create_parser()], add_help=False)
        command.set_defaults(handler=module.run, command_parser=command)
    args = parser.parse_args(argv)
    args.handler(args, args.command_parser)
