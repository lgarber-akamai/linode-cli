"""
Contains all structures used to render documentation templates.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from io import StringIO
from typing import Dict, List, Optional, Self, Set

from linodecli.baked import OpenAPIOperation
from linodecli.baked.operation import OpenAPIOperationParameter
from linodecli.baked.request import OpenAPIRequestArg
from linodecli.baked.response import OpenAPIResponseAttr
from linodecli.cli import CLI
from linodecli.documentation.util import (
    _format_usage_text,
    _markdown_to_rst,
    _normalize_padding,
)
from linodecli.helpers import sorted_actions_smart

# Manual corrections to the generated "pretty" names for command groups.
GROUP_NAME_CORRECTIONS = {
    "lke": "LKE",
    "nodebalancers": "NodeBalancer",
    "sshkeys": "SSH Keys",
    "vlans": "VLANs",
    "vpcs": "VPCs",
}


@dataclass
class FilterableAttribute:
    """
    Represents a single filterable attribute for a list command/action.
    """

    name: str
    type: str

    description: Optional[str]

    @classmethod
    def from_openapi(cls, attr: OpenAPIResponseAttr) -> Self:
        """
        Returns a new FilterableAttribute object initialized using values
        from the given filterable OpenAPI response attribute.

        :param attr: The OpenAPI response attribute to initialize the object with.

        :returns: The initialized object.
        """

        return cls(
            name=attr.name,
            type=(
                attr.datatype
                if attr.item_type is None
                else f"{attr.datatype}[{attr.item_type}]"
            ),
            description=(
                _markdown_to_rst(attr.description)
                if attr.description != ""
                else None
            ),
        )


@dataclass
class Argument:
    """
    Represents a single argument for a command/action.
    """

    path: str
    required: bool
    type: str

    is_json: bool = False
    is_nullable: bool = False
    is_parent: bool = False
    depth: int = 0
    description: Optional[str] = None

    @classmethod
    def from_openapi(cls, arg: OpenAPIRequestArg) -> Self:
        """
        Returns a new Argument object initialized using values
        from the given OpenAPI request argument.

        :param arg: The OpenAPI request argument to initialize the object with.

        :returns: The initialized object.
        """

        return cls(
            path=arg.path,
            required=arg.required,
            type=(
                arg.datatype
                if arg.item_type is None
                else f"{arg.datatype}[{arg.item_type}]"
            ),
            is_json=arg.format == "json",
            is_nullable=arg.nullable,
            is_parent=arg.is_parent,
            depth=arg.depth,
            description=(
                _markdown_to_rst(arg.description)
                if arg.description != ""
                else None
            ),
        )


@dataclass
class Param:
    """
    Represents a single URL parameter for a command/action.
    """

    name: str
    type: str

    description: Optional[str] = None

    @classmethod
    def from_openapi(cls, param: OpenAPIOperationParameter) -> Self:
        """
        Returns a new Param object initialized using values
        from the given OpenAPI parameter.

        :param param: The OpenAPI parameter to initialize the object with.

        :returns: The initialized object.
        """

        return cls(
            name=param.name,
            type=param.type,
            description=(
                _markdown_to_rst(param.description)
                if param.description is not None
                else None
            ),
        )


@dataclass
class ArgumentSection:
    """
    Represents a single section of arguments.
    """

    name: str
    arguments: List[Argument]


@dataclass
class Action:
    """
    Represents a single generated Linode CLI command/action.
    """

    command: str
    action: List[str]

    usage: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    api_documentation_url: Optional[str] = None
    deprecated: bool = False
    parameters: List[Param] = field(default_factory=lambda: [])
    samples: List[str] = field(default_factory=lambda: [])
    filterable_attrs: List[FilterableAttribute] = field(
        default_factory=lambda: []
    )
    argument_sections: List[ArgumentSection] = field(default_factory=lambda: [])
    argument_sections_names: Set[str] = field(default_factory=lambda: {})

    @classmethod
    def from_openapi(cls, operation: OpenAPIOperation) -> Self:
        """
        Returns a new Action object initialized using values
        from the given operation.

        :param operation: The operation to initialize the object with.

        :returns: The initialized object.
        """

        result = cls(
            command=operation.command,
            action=(
                operation.action
                if isinstance(operation.action, list)
                else [operation.action]
            ),
            summary=_markdown_to_rst(operation.summary),
            description=(
                _markdown_to_rst(operation.description)
                if operation.description != ""
                else None
            ),
            api_documentation_url=operation.docs_url,
            deprecated=operation.deprecated,
        )

        if operation.samples:
            result.samples = [
                _normalize_padding(sample["source"])
                for sample in operation.samples
            ]

        if operation.params:
            result.parameters = [
                Param.from_openapi(param) for param in operation.params
            ]

        if operation.args:
            sections = defaultdict(lambda: [])

            for arg in operation.args:
                if not isinstance(arg, OpenAPIRequestArg):
                    continue

                sections[arg.prefix or ""].append(Argument.from_openapi(arg))

            result.argument_sections = sorted(
                [
                    ArgumentSection(
                        name=k,
                        arguments=sorted(
                            v, key=lambda arg: (not arg.required, arg.path)
                        ),
                    )
                    for k, v in sections.items()
                ],
                key=lambda section: section.name,
            )

            result.argument_sections_names = set(sections.keys())

        if operation.method == "get" and operation.response_model.is_paginated:
            result.filterable_attrs = sorted(
                [
                    FilterableAttribute.from_openapi(attr)
                    for attr in operation.response_model.attrs
                    if attr.filterable
                ],
                key=lambda v: v.name,
            )

        result.usage = Action._get_usage(operation)

        return result

    @staticmethod
    def _get_usage(operation: OpenAPIOperation) -> str:
        """
        Returns the formatted argparse usage string for the given operation.

        :param: operation: The operation to get the usage string for.

        :returns: The formatted usage string.
        """

        usage_io = StringIO()
        operation.build_parser()[0].print_usage(file=usage_io)

        return _format_usage_text(usage_io.getvalue())


@dataclass
class Group:
    """
    Represents a single "group" of commands/actions as defined by the Linode API.
    """

    name: str
    pretty_name: str
    actions: List[Action]

    @classmethod
    def from_openapi(
        cls, name: str, group: Dict[str, OpenAPIOperation]
    ) -> Self:
        """
        Returns a new Group object initialized using values
        from the given name and group mapping.

        :param name: The name/key of the group.
        :param group: A mapping between action names and their corresponding OpenAPIOperations.

        :returns: The initialized object.
        """

        return cls(
            name=name,
            pretty_name=(
                GROUP_NAME_CORRECTIONS[name]
                if name in GROUP_NAME_CORRECTIONS
                else name.title().replace("-", " ")
            ),
            actions=sorted_actions_smart(
                [Action.from_openapi(action) for action in group.values()],
                key=lambda v: v.action[0],
            ),
        )


@dataclass
class Root:
    """
    The root template data structure for the Linode CLI.
    """

    groups: List[Group]

    @classmethod
    def from_cli(cls, cli: CLI) -> Self:
        """
        Returns a new Root object initialized using values
        from the given CLI.

        :param cli: The CLI to initialize the object with.

        :returns: The initialized object.
        """

        return cls(
            groups=sorted(
                [
                    Group.from_openapi(key, group)
                    for key, group in cli.ops.items()
                ],
                key=lambda v: v.name,
            ),
        )


@dataclass
class BuildMeta:
    """
    Contains metadata about a single documentation build.
    """

    cli_version: str
    api_spec_version: str
