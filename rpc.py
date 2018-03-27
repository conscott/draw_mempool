#!/usr/bin/env python3
import decimal
import json
import re
import subprocess
JSONDecodeError = getattr(json, "JSONDecodeError", ValueError)

"""
This is just a bitcoin-cli wrapper that serializes output
to python primitives.

This has been copied almost directly from the bitcoin test_framework
"""


class JSONRPCException(Exception):
    def __init__(self, rpc_error):
        try:
            errmsg = '%(message)s (%(code)i)' % rpc_error
        except (KeyError, TypeError):
            errmsg = ''
        super().__init__(errmsg)
        self.error = rpc_error


class NodeCLIAttr:
    def __init__(self, cli, command):
        self.cli = cli
        self.command = command

    def __call__(self, *args, **kwargs):
        return self.cli.send_cli(self.command, *args, **kwargs)

    def get_request(self, *args, **kwargs):
        return lambda: self(*args, **kwargs)


class NodeCLI():
    """Interface to bitcoin-cli for an individual node"""

    def __init__(self, binary, datadir=None):
        self.options = []
        self.binary = binary
        self.datadir = datadir
        self.input = None

    def __call__(self, *options, input=None):
        # NodeCLI is callable with bitcoin-cli command-line options
        cli = NodeCLI(self.binary)
        cli.options = [str(o) for o in options]
        cli.input = input
        return cli

    def __getattr__(self, command):
        return NodeCLIAttr(self, command)

    def batch(self, requests):
        results = []
        for request in requests:
            try:
                results.append(dict(result=request()))
            except JSONRPCException as e:
                results.append(dict(error=e))
        return results

    def send_cli(self, command=None, *args, **kwargs):
        """Run bitcoin-cli command. Deserializes returned string as python object."""

        pos_args = [str(arg) for arg in args]
        named_args = [str(key) + "=" + str(value) for (key, value) in kwargs.items()]
        assert not (pos_args and named_args), "Cannot use positional arguments and named arguments in the same bitcoin-cli call"
        p_args = [self.binary] + self.options
        if self.datadir:
            p_args += ["-datadir=" + self.datadir]
        if named_args:
            p_args += ["-named"]
        if command is not None:
            p_args += [command]
        p_args += pos_args + named_args
        # print("CALL: %s" % p_args)
        process = subprocess.Popen(p_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        cli_stdout, cli_stderr = process.communicate(input=self.input)
        returncode = process.poll()
        if returncode:
            match = re.match(r'error code: ([-0-9]+)\nerror message:\n(.*)', cli_stderr)
            if match:
                code, message = match.groups()
                raise JSONRPCException(dict(code=int(code), message=message))
            # Ignore cli_stdout, raise with cli_stderr
            raise subprocess.CalledProcessError(returncode, self.binary, output=cli_stderr)
        try:
            return json.loads(cli_stdout, parse_float=decimal.Decimal)
        except JSONDecodeError:
            return cli_stdout.rstrip("\n")
