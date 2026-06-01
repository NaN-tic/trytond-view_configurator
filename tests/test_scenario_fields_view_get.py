import unittest

from proteus import Model
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules
from trytond.transaction import Transaction


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('view_configurator')

        Configurator = Model.get('view.configurator')
        ConfiguratorLine = Model.get('view.configurator.line')
        ConfiguratorLineField = Model.get('view.configurator.line.field')
        IrModel = Model.get('ir.model')
        IrModelField = Model.get('ir.model.field')

        model, = IrModel.find([
            ('name', '=', 'ir.attachment'),
            ])
        field, = IrModelField.find([
            ('model.name', '=', 'ir.attachment'),
            ('name', '=', 'name'),
            ])

        configurator = Configurator(model=model)
        configurator.save()

        ConfiguratorLine.delete(list(configurator.lines))
        configurator.reload()

        line = ConfiguratorLineField(view=configurator, field=field)
        line.save()

        Attachment = config.pool.get('ir.attachment')
        with Transaction().start(config.database_name, config.user) as transaction:
            transaction.context = config.context
            view = Attachment.fields_view_get(view_type='tree')

        self.assertEqual(view['type'], 'tree')
        self.assertEqual(view['arch'], '<tree><field name="name"/></tree>')
