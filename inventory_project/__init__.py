# Python 3.14 compatibility patch for Django 4.2
# Django 4.2's BaseContext.__copy__ uses `self.__dict__` which doesn't exist
# on dict subclasses in Python 3.14, causing AttributeError.
import django.template.context
import copy

_original_bc_copy = django.template.context.BaseContext.__copy__


def _patched_basecontext_copy(self):
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate


django.template.context.BaseContext.__copy__ = _patched_basecontext_copy

# Also patch RenderContext if needed
if hasattr(django.template.context, "RenderContext"):
    _original_rc_copy = django.template.context.RenderContext.__copy__

    def _patched_rendercontext_copy(self):
        duplicate = django.template.context.BaseContext.__new__(
            django.template.context.RenderContext
        )
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    django.template.context.RenderContext.__copy__ = _patched_rendercontext_copy
