"""
Handles formatting the output of commands used in Linode CLI
"""
import json
from enum import Enum
from sys import stdout
from typing import IO, Any, Dict, List, Optional, Union, cast

from rich import box
from rich import print as rprint
from rich.console import OverflowMethod
from rich.table import Column, Table
from rich.text import Text

from linodecli.baked.response import OpenAPIResponse, OpenAPIResponseAttr


class OutputMode(Enum):
    """
    Enum for output modes
    """

    table = 1
    delimited = 2
    json = 3
    markdown = 4
    ascii_table = 5


class OutputHandler:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """
    Handles formatting the output of commands used in Linode CLI
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        mode=OutputMode.table,
        delimiter="\t",
        headers=True,
        pretty_json=False,
        columns=None,
        disable_truncation=False,
        suppress_warnings=False,
        column_width=None,
    ):
        self.mode = mode
        self.delimiter = delimiter
        self.pretty_json = pretty_json
        self.headers = headers
        self.columns = columns
        self.suppress_warnings = suppress_warnings

        self.disable_truncation = disable_truncation
        self.column_width = column_width

        # Used to track whether a warning has already been printed
        self.has_warned = False

    def print(
        self,
        data: List[Union[str, dict]],
        columns: List[str],
        title: Optional[str] = None,
        to: IO[str] = stdout,
    ):  # pylint: disable=too-many-arguments
        """
        :param data: The data to display
        :type data: list[str] or list[dict]
        :param title: The title to display on a table
        :type title: Optional[str]
        :param to: Where to print output to
        :type to: stdout, stderr or file
        :param columns: The columns to display
        :type columns: Optional[List[str]]
        """
        self._print(columns, data, columns, title, to)

    def print_response(
        self,
        response_model: OpenAPIResponse,
        data: List[Union[str, dict]],
        to: IO[str] = stdout,
    ):  # pylint: disable=too-many-arguments
        """
        :param response_model: The Model corresponding to this response
        :type response_model: OpenAPIResponse
        :param data: The data to display
        :type data: list[str] or list[dict]
        :param title: The title to display on a table
        :type title: Optional[str]
        :param to: Where to print output to
        :type to: stdout, stderr or file
        :param columns: The columns to display
        :type columns: Optional[List[str]]
        """
        for table in [""] + response_model.subtables:
            new_data = self._resolve_data_for_table(table, data)

            columns = self._get_columns(
                response_model.get_attributes_for_table(table)
            )

            if len(columns) < 1:
                continue

            header = [c.column_name for c in columns]

            self._print(header, new_data, columns, table, to)

    def _print(self, header, data, columns, title, to):
        # We need to use lambdas here since we don't want unused function params
        output_mode_to_func = {
            OutputMode.table: lambda: self._table_output(
                header, data, columns, title, to
            ),
            OutputMode.ascii_table: lambda: self._table_output(
                header, data, columns, title, to, box_style=box.ASCII
            ),
            OutputMode.delimited: lambda: self._delimited_output(
                header, data, columns, to
            ),
            OutputMode.json: lambda: self._json_output(header, data, to),
            OutputMode.markdown: lambda: self._table_output(
                header, data, columns, title, to, box_style=box.MARKDOWN
            ),
        }

        if self.mode not in output_mode_to_func:
            raise RuntimeError(f"Unknown output mode: {self.mode}")

        output_mode_to_func[self.mode]()

    @staticmethod
    def _resolve_data_for_table(path: str, data: List[Dict[str, Any]]):
        if len(data) == 0 or path == "":
            return data

        current_data = data[0]

        for v in path.split("."):
            if v not in current_data:
                raise ValueError(f"Sublist path not found in data: {path}")

            current_data = current_data[v]

        return (
            current_data if isinstance(current_data, list) else [current_data]
        )

    def _get_columns(self, attrs: List[OpenAPIResponseAttr]):
        """
        Based on the configured columns, returns columns from a response model
        """
        if self.columns is None:
            columns = [
                attr
                for attr in sorted(attrs, key=lambda c: c.display)
                if attr.display
            ]
        elif self.columns == "*":
            columns = list(attrs)
        else:
            columns = []
            for col in self.columns.split(","):
                for attr in attrs:
                    if attr.column_name == col:
                        attrs.remove(attr)
                        columns.append(attr)
                        continue

        if not columns:
            # either they selected nothing, or the model wasn't setup for CLI
            # display - either way, display everything
            columns = attrs

        return columns

    def _table_output(
        self, header, data, columns, title, to, box_style=box.SQUARE
    ):  # pylint: disable=too-many-arguments
        """
        Pretty-prints data in a table
        """

        content = self._build_output_content(
            data,
            columns,
            value_transform=lambda attr, v: str(attr.render_value(v)),
        )

        # Determine the rich overflow mode to use
        # for each column.
        overflow_mode = cast(
            OverflowMethod, "fold" if self.disable_truncation else "ellipsis"
        )

        # Convert the headers into column objects
        # so we can override the overflow method.
        header_columns = [
            Column(v, overflow=overflow_mode, max_width=self.column_width)
            for v in header
        ]

        tab = Table(
            *header_columns,
            header_style="",
            box=box_style,
            show_header=self.headers,
        )
        for row in content:
            row = [Text.from_ansi(item) for item in row]
            tab.add_row(*row)

        if title is not None:
            tab.title = title

        rprint(tab, file=to)

    def _delimited_output(self, header, data, columns, to):
        """
        Prints data in delimited format with the given delimiter
        """
        content = self._build_output_content(
            data,
            columns,
            header=header,
            value_transform=lambda attr, v: attr.get_string(v),
        )

        for row in content:
            print(self.delimiter.join(row), file=to)

    def _json_output(self, header, data, to):
        """
        Prints data in JSON format
        """
        content = []
        if len(data) and isinstance(data[0], dict):  # we got delimited json in
            # parse down to the value we display
            for row in data:
                content.append(self._select_json_elements(header, row))
        else:  # this is a list
            for row in data:
                content.append(dict(zip(header, row)))

        print(
            json.dumps(
                content,
                indent=2 if self.pretty_json else None,
                sort_keys=self.pretty_json,
            ),
            file=to,
        )

    @staticmethod
    def _select_json_elements(keys, json_res):
        """
        Returns a dict filtered down to include only the selected keys.  Walks
        paths to handle nested dicts
        """
        ret = {}
        for k, v in json_res.items():
            if k in keys:
                ret[k] = v
            elif isinstance(v, dict):
                v = OutputHandler._select_json_elements(keys, v)
                if v:
                    ret[k] = v
        return ret

    def _build_output_content(
        self,
        data,
        columns,
        header=None,
        value_transform=lambda attr, model: model,
    ):
        """
        Returns the `content` to be displayed by the corresponding output function.
        `value_transform` allows functions to specify how each value should be formatted.
        """

        content = []

        if self.headers and header is not None:
            content = [header]

        # We're not using models here
        # We won't apply transforms here since no formatting is being applied
        if isinstance(columns[0], str):
            return content + data

        for model in data:
            content.append([value_transform(attr, model) for attr in columns])

        return content
