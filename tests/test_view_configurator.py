# This file is part view_configurator module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import unittest


from trytond.tests.test_tryton import ModuleTestCase
from trytond.tests.test_tryton import suite as test_suite


class ViewConfiguratorTestCase(ModuleTestCase):
    'Test View Configurator module'
    module = 'view_configurator'


def suite():
    suite = test_suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            ViewConfiguratorTestCase))
    return suite
