"""GameForge IDE — Agentic Game Development Environment."""
from __future__ import annotations

import json as _json
import pydantic as _pydantic

__version__ = "1.0.0"
__all__ = ["__version__"]


def _install_pydantic_v2_compat() -> None:
    if not getattr(_pydantic, "__version__", "").startswith("1."):
        return
    if getattr(_pydantic, "_gf_v2_compat_installed", False):
        return

    from pydantic import BaseModel as _BaseModel, Field as _OrigField, validator as _validator, root_validator as _root_validator
    from pydantic.error_wrappers import ErrorWrapper as _ErrorWrapper, ValidationError as _ValidationError
    from pydantic.fields import FieldInfo as _FieldInfo
    from pydantic.main import ModelMetaclass as _ModelMetaclass
    import pydantic.schema as _p_schema
    import pydantic.fields as _p_fields
    _orig_get_ann = _p_schema.get_annotation_from_field_info

    def _safe_get_ann(annotation, field_info, field_name, validate_assignment=False):
        try:
            return _orig_get_ann(annotation, field_info, field_name, validate_assignment)
        except ValueError:
            return annotation

    _p_schema.get_annotation_from_field_info = _safe_get_ann
    if hasattr(_p_fields, "get_annotation_from_field_info"):
        _p_fields.get_annotation_from_field_info = _safe_get_ann

    class AliasChoices:
        def __init__(self, *choices: str) -> None:
            self.choices = tuple(choices)

    def ConfigDict(**kwargs):
        return dict(kwargs)

    _orig_field = _OrigField

    def Field(*args, pattern=None, validation_alias=None, **kwargs):
        if pattern is not None and "regex" not in kwargs:
            kwargs["regex"] = pattern
        if validation_alias is not None:
            kwargs["validation_alias"] = validation_alias
            if isinstance(validation_alias, str) and "alias" not in kwargs:
                kwargs["alias"] = validation_alias
        return _orig_field(*args, **kwargs)

    import inspect as _inspect

    class _ValidationInfo:
        def __init__(self, field_name: str, data: dict) -> None:
            self.field_name = field_name
            self.data = data

    def field_validator(*fields: str, mode: str = "after", **kwargs):
        pre = (mode == "before")

        def _decorator(fn):
            target = fn.__func__ if isinstance(fn, classmethod) else fn
            params = list(_inspect.signature(target).parameters.keys())
            if len(params) >= 3:
                def _wrapped(cls, v, values, field):
                    return target(cls, v, _ValidationInfo(field.name, values))

                _wrapped.__name__ = getattr(target, "__name__", "validator")
                return _validator(*fields, pre=pre, allow_reuse=True)(_wrapped)
            else:
                def _wrapped2(cls, v):
                    return target(cls, v)

                _wrapped2.__name__ = getattr(target, "__name__", "validator")
                return _validator(*fields, pre=pre, allow_reuse=True)(_wrapped2)

        return _decorator

    def model_validator(*, mode: str = "after"):
        def _decorator(fn):
            target = fn.__func__ if isinstance(fn, classmethod) else fn
            if mode == "before":
                @_root_validator(pre=True, allow_reuse=True)
                def _pre_wrap(cls, values):
                    return target(cls, values)

                return _pre_wrap
            else:
                setattr(target, "_gf_model_after_validator", True)
                return target

        return _decorator

    _orig_meta_new = _ModelMetaclass.__new__

    def _compat_meta_new(mcs, name, bases, namespace, **kwargs):
        mc = namespace.pop("model_config", None)
        after_validators = []
        for b in bases:
            after_validators.extend(getattr(b, "_gf_after_validators", []))
        for k, v in list(namespace.items()):
            raw_fn = v.__func__ if isinstance(v, classmethod) else v
            if getattr(raw_fn, "_gf_model_after_validator", False):
                after_validators.append(raw_fn)

        if mc is not None and isinstance(mc, dict):
            orig_cfg = namespace.get("Config")
            base_cfgs = [getattr(b, "Config", None) for b in bases if hasattr(b, "Config")]
            cfg_parents = tuple([orig_cfg] if orig_cfg else base_cfgs) or (object,)
            cfg_dict = {}
            if "extra" in mc:
                cfg_dict["extra"] = mc["extra"]
            if mc.get("populate_by_name"):
                cfg_dict["allow_population_by_field_name"] = True
            if mc.get("validate_assignment"):
                cfg_dict["validate_assignment"] = True
            if mc.get("frozen"):
                cfg_dict["allow_mutation"] = False
            namespace["Config"] = type("Config", cfg_parents, cfg_dict)

        anns = namespace.get("__annotations__", {})
        for f_name, ann in anns.items():
            ann_str = str(ann).lower()
            if any(k in ann_str for k in ("list[", "list ", "tuple[", "set[")):
                f_val = namespace.get(f_name)
                if isinstance(f_val, _FieldInfo):
                    if getattr(f_val, "min_length", None) is not None and getattr(f_val, "min_items", None) is None:
                        f_val.min_items = f_val.min_length
                        f_val.min_length = None
                    if getattr(f_val, "max_length", None) is not None and getattr(f_val, "max_items", None) is None:
                        f_val.max_items = f_val.max_length
                        f_val.max_length = None

        cls = _orig_meta_new(mcs, name, bases, namespace, **kwargs)
        cls._gf_after_validators = after_validators
        return cls

    _ModelMetaclass.__new__ = _compat_meta_new

    _orig_bm_init = _BaseModel.__init__

    def _compat_bm_init(self, **data):
        fields_map = getattr(self, "__fields__", {})
        for f_name, m_field in fields_map.items():
            val_alias = m_field.field_info.extra.get("validation_alias")
            if val_alias is not None and f_name not in data:
                choices = val_alias.choices if isinstance(val_alias, AliasChoices) else (str(val_alias),)
                for ch in choices:
                    if ch in data:
                        data[f_name] = data.pop(ch)
                        break
        _orig_bm_init(self, **data)
        for v_fn in getattr(self.__class__, "_gf_after_validators", ()):
            try:
                v_fn(self)
            except _ValidationError:
                raise
            except Exception as exc:
                raise _ValidationError([_ErrorWrapper(exc, loc="__root__")], self.__class__) from exc

    _BaseModel.__init__ = _compat_bm_init

    def _model_dump(self, *, mode: str = "python", by_alias: bool = False, exclude_none: bool = False, **kwargs):
        if mode == "json":
            return _json.loads(self.json(by_alias=by_alias, exclude_none=exclude_none))
        return self.dict(by_alias=by_alias, exclude_none=exclude_none, **kwargs)

    def _model_dump_json(self, *, indent: int | None = None, by_alias: bool = False, exclude_none: bool = False, **kwargs) -> str:
        return self.json(indent=indent, by_alias=by_alias, exclude_none=exclude_none, **kwargs)

    @classmethod
    def _model_validate(cls, obj, **kwargs):
        if isinstance(obj, cls):
            return obj
        return cls.parse_obj(obj)

    @classmethod
    def _model_validate_json(cls, json_data: str | bytes, **kwargs):
        return cls.parse_raw(json_data)

    @classmethod
    def _model_json_schema(cls, **kwargs):
        return cls.schema(**kwargs)

    @classmethod
    def _model_rebuild(cls, **kwargs):
        try:
            cls.update_forward_refs()
        except Exception:
            pass

    def _model_copy(self, *, update=None, deep: bool = False):
        return self.copy(update=update, deep=deep)

    class _ModelFieldsDescriptor:
        def __get__(self, obj, cls=None):
            target = cls if cls is not None else type(obj)
            return getattr(target, "__fields__", {})

    _BaseModel.model_dump = _model_dump
    _BaseModel.model_dump_json = _model_dump_json
    _BaseModel.model_validate = _model_validate
    _BaseModel.model_validate_json = _model_validate_json
    _BaseModel.model_json_schema = _model_json_schema
    _BaseModel.model_rebuild = _model_rebuild
    _BaseModel.model_copy = _model_copy
    if not hasattr(_BaseModel, "model_fields"):
        _BaseModel.model_fields = _ModelFieldsDescriptor()

    _pydantic.AliasChoices = AliasChoices
    _pydantic.ConfigDict = ConfigDict
    _pydantic.Field = Field
    _pydantic.field_validator = field_validator
    _pydantic.model_validator = model_validator
    _pydantic._gf_v2_compat_installed = True


_install_pydantic_v2_compat()
