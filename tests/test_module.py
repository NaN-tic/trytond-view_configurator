
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.pool import Pool


class ViewConfiguratorTestCase(ModuleTestCase):
    'Test ViewConfigurator module'
    module = 'view_configurator'

    @with_transaction()
    def test_attachment(self):
        'Create custom view ir.attachment'
        pool = Pool()
        Configurator = pool.get('view.configurator')
        ConfiguratorLine = pool.get('view.configurator.line')
        Model = pool.get('ir.model')
        ModelField = pool.get('ir.model.field')
        Attachment = pool.get('ir.attachment')

        model, = Model.search([
            ('model', '=', 'ir.attachment')
            ], limit=1)
        fields = dict((f.name, f) for f in ModelField.search([
            ('model.model', '=', 'ir.attachment')
            ]))

        conf1 = Configurator(
            model=model,
            )
        conf1.save()
        self.assertTrue(conf1.id)
        self.assertIsNotNone(conf1.lines)

        ConfiguratorLine.delete(conf1.lines)
        conf1 = Configurator(conf1.id)
        conf1.lines = [{
            'type': 'ir.model.field',
            'field': fields.get('name'),
            }]
        conf1.save()
        self.assertEqual(len(conf1.lines), 1)

        view = Attachment.fields_view_get(view_type='tree')
        self.assertEqual(view['type'], 'tree')
        self.assertEqual(view['arch'], '<tree><field name="name"/></tree>')

    @with_transaction()
    def test_model(self):
        'Create custom view ir.model.field'
        pool = Pool()
        Configurator = pool.get('view.configurator')
        ConfiguratorLine = pool.get('view.configurator.line')
        Model = pool.get('ir.model')
        ModelField = pool.get('ir.model.field')
        View = pool.get('ir.ui.view')

        view_tree, = View.search(['name', '=', 'model_field_list'], limit=1)
        view_form, = View.search(['name', '=', 'model_field_form'], limit=1)

        model, = Model.search([
            ('model', '=', 'ir.model.field')
            ], limit=1)
        fields = dict((f.name, f) for f in ModelField.search([
            ('model.model', '=', 'ir.model.field')
            ]))

        conf1 = Configurator(
            model=model,
            )
        conf1.save()
        self.assertTrue(conf1.id)
        self.assertIsNotNone(conf1.lines)

        ConfiguratorLine.delete(conf1.lines)
        conf1 = Configurator(conf1.id)
        conf1.lines = [{
            'type': 'ir.model.field',
            'field': fields.get('name'),
            }, {
                'type': 'ir.model.field',
                'field': fields.get('access'),
            }]
        conf1.save()
        self.assertEqual(len(conf1.lines), 2)

        # test model tree view + one2many field tree view
        view1 = ModelField.fields_view_get(view_id=view_tree.id)
        view2 = ModelField.fields_view_get(view_type='tree')
        for view in (view1, view2):
            self.assertEqual(view['type'], 'tree')
            self.assertEqual(view['arch'],
                '<tree><field name="name"/><field name="access"/></tree>')

        # check custom tree view from fields (o2m field)
        view3 = Model.fields_view_get()
        # fields <filename> views tree arch
        self.assertEqual(view3['fields']['fields']['views']['tree']['arch'],
            view1['arch'])

        view4 = ModelField.fields_view_get(view_id=view_form.id)
        view5 = ModelField.fields_view_get(view_type='form')
        for view in (view4, view5):
            self.assertEqual(view['type'], 'form')
            self.assertEqual(view['arch'].startswith("<form><label"), True)

del ModuleTestCase
