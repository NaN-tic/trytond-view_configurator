# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import Pool
from trytond.model import ModelView
from . import configurator

def register():
    Pool.register(
        configurator.ViewConfigurator,
        configurator.ViewConfiguratorLine,
        configurator.ViewConfiguratorSnapshot,
        configurator.ViewConfiguratorLineField,
        configurator.ViewConfiguratorLineButton,
        module='view_configurator', type_='model')
    Pool.register_mixin(
        configurator.ModelViewMixin, ModelView, module='custom_view')
