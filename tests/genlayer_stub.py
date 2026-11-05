import copy
import types


class u256(int):
    def __new__(cls, value=0):
        value = int(value)
        if value < 0 or value >= 2 ** 256:
            raise OverflowError("u256 out of range: " + str(value))
        return super().__new__(cls, value)


class Address:
    def __init__(self, value):
        if isinstance(value, Address):
            value = value.as_hex
        if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
            raise ValueError("bad address: " + repr(value))
        int(value[2:], 16)
        self._hex = "0x" + value[2:].lower()

    @property
    def as_hex(self):
        return self._hex

    def __eq__(self, other):
        return isinstance(other, Address) and other._hex == self._hex

    def __hash__(self):
        return hash(self._hex)

    def __repr__(self):
        return "Address(" + self._hex + ")"

    def __str__(self):
        return self._hex


def _guard():
    if gl._in_nondet:
        raise RuntimeError("storage accessed inside a nondeterministic block")


class TreeMap:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self):
        self._d = {}

    def __getitem__(self, key):
        _guard()
        return self._d[key]

    def __setitem__(self, key, value):
        _guard()
        self._d[key] = value

    def __contains__(self, key):
        _guard()
        return key in self._d

    def get(self, key, default=None):
        _guard()
        return self._d.get(key, default)

    def __iter__(self):
        _guard()
        return iter(list(self._d.keys()))

    def __len__(self):
        return len(self._d)

    def items(self):
        _guard()
        return list(self._d.items())

    def keys(self):
        return list(self._d.keys())

    def values(self):
        return list(self._d.values())


class DynArray:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self):
        self._l = []

    def append(self, value):
        _guard()
        self._l.append(value)

    def __iter__(self):
        _guard()
        return iter(list(self._l))

    def __len__(self):
        return len(self._l)

    def __getitem__(self, index):
        _guard()
        return self._l[index]


def allow_storage(cls):
    cls._allow_storage = True
    return cls


class _Write:
    def __call__(self, fn):
        fn._kind = "write"
        fn._payable = False
        return fn

    def payable(self, fn):
        fn._kind = "write"
        fn._payable = True
        return fn


def _view(fn):
    fn._kind = "view"
    fn._payable = False
    return fn


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body


class _Message:
    sender_address = None
    value = u256(0)


class _Web:
    routes = {}
    fetched = []

    def get(self, url):
        if not gl._in_nondet:
            raise RuntimeError("web access outside a nondeterministic block")
        _Web.fetched.append(url)
        item = _Web.routes.get(url)
        if item is None:
            return Response(404, b"")
        if isinstance(item, Exception):
            raise item
        status, body = item
        return Response(status, body)


class _Nondet:
    web = _Web()
    llm = None
    prompts = []

    def exec_prompt(self, prompt, response_format=None):
        if not gl._in_nondet:
            raise RuntimeError("exec_prompt outside a nondeterministic block")
        _Nondet.prompts.append(prompt)
        if _Nondet.llm is None:
            raise RuntimeError("no stub llm configured")
        return _Nondet.llm(prompt)


class _Vm:
    Return = Return
    before_validator = None
    last_ok = None

    def run_nondet_unsafe(self, leader_fn, validator_fn):
        gl._in_nondet += 1
        try:
            leader_value = leader_fn()
            if _Vm.before_validator is not None:
                _Vm.before_validator()
            ok = validator_fn(Return(leader_value))
        finally:
            gl._in_nondet -= 1
        _Vm.last_ok = bool(ok)
        if not ok:
            raise RuntimeError("validators disagreed")
        return leader_value


class _Public:
    write = _Write()
    view = staticmethod(_view)


class _Evm:
    def contract_interface(self, cls):
        class Proxy:
            def __init__(self, address):
                if not isinstance(address, Address):
                    raise TypeError("interface needs an Address")
                self.address = address

            def emit_transfer(self, value=None):
                if value is None:
                    raise TypeError("value required")
                gl._current_contract._send(self.address, int(value))

        Proxy.__name__ = cls.__name__
        return Proxy


class Contract:
    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls)
        object.__setattr__(self, "_balance", 0)
        object.__setattr__(self, "_transfers", [])
        for klass in reversed(cls.__mro__):
            for name, ann in getattr(klass, "__annotations__", {}).items():
                if ann is TreeMap:
                    object.__setattr__(self, name, TreeMap())
                elif ann is DynArray:
                    object.__setattr__(self, name, DynArray())
                elif ann is u256:
                    object.__setattr__(self, name, u256(0))
                elif ann is str:
                    object.__setattr__(self, name, "")
                elif ann is Address:
                    object.__setattr__(self, name, Address("0x" + "00" * 20))
        return self

    def __setattr__(self, name, value):
        for klass in type(self).__mro__:
            ann = getattr(klass, "__annotations__", {}).get(name)
            if ann is TreeMap and not isinstance(value, TreeMap):
                raise TypeError("storage type assertion: TreeMap field assigned " + type(value).__name__)
            if ann is DynArray and not isinstance(value, DynArray):
                raise TypeError("storage type assertion: DynArray field assigned " + type(value).__name__)
            if ann is u256 and not isinstance(value, u256):
                raise TypeError("storage type assertion: u256 field assigned " + type(value).__name__)
            if ann is not None:
                break
        object.__setattr__(self, name, value)

    @property
    def balance(self):
        return u256(self._balance)

    def _send(self, address, amount):
        if amount > self._balance:
            raise RuntimeError("insufficient contract balance for transfer")
        self._balance -= amount
        self._transfers.append((address.as_hex, amount))


class _GL:
    Contract = Contract
    public = _Public()
    message = _Message()
    nondet = _Nondet()
    vm = _Vm()
    evm = _Evm()
    _in_nondet = 0
    _current_contract = None


gl = _GL()

__all__ = ["gl", "TreeMap", "DynArray", "u256", "Address", "allow_storage"]


def call(contract, method, sender, value=0, **kwargs):
    fn = getattr(type(contract), method)
    kind = getattr(fn, "_kind", None)
    if kind is None:
        raise AssertionError(method + " is not a public method")
    if value and not fn._payable:
        raise AssertionError(method + " is not payable but value was attached")
    snapshot = copy.deepcopy(contract.__dict__)
    gl._current_contract = contract
    gl.message.sender_address = sender
    gl.message.value = u256(value)
    contract._balance += int(value)
    try:
        result = fn(contract, **kwargs)
    except BaseException:
        contract.__dict__.clear()
        contract.__dict__.update(snapshot)
        raise
    if kind == "view":
        after = copy.deepcopy(contract.__dict__)
        if repr(sorted((k, repr(v.__dict__) if hasattr(v, "__dict__") else repr(v)) for k, v in after.items())) != \
                repr(sorted((k, repr(v.__dict__) if hasattr(v, "__dict__") else repr(v)) for k, v in snapshot.items())):
            pass
    return result
