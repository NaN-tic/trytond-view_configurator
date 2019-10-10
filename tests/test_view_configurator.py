# This file is part view_configurator module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import unittest
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.tests.test_tryton import suite as test_suite
from trytond.pool import Pool


class ViewConfiguratorTestCase(ModuleTestCase):
    'Test View Configurator module'
    module = 'view_configurator'

    @with_transaction()
    def test_attachment(self):
        'Create view attachment'
        pool = Pool()
        Configuration = pool.get('view.configurator')
        Model = pool.get('ir.model')
        Fields = pool.get('ir.model.field')

        model, = Model.search([
            ('model', '=', 'ir.attachment')
            ], limit=1)
        fields = dict((f.name, f) for f in Fields.search([
            ('model.model', '=', 'ir.attachment')
            ]))

        conf1, = Configuration.create([{
                    'model': model,
                    'lines': [('create', [{
                        'type': 'ir.model.field',
                        'field': fields.get('name'),
                        }])],
                    }])
        self.assertTrue(conf1.id)


def suite():
    suite = test_suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            ViewConfiguratorTestCase))
    return suite
