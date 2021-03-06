import bpy
import nodeitems_utils

def setup_node_tree(node_tree: bpy.types.NodeTree, nodes_def):
    nodes = node_tree.nodes
    links = node_tree.links

    if not isinstance(nodes_def, dict):
        raise TypeError(f"nodes_def has type '{type(nodes_def).__name__}', expected 'dict'")
    for name, (node_type, attrs, inputs) in nodes_def.items():
        node = nodes.new(node_type)
        node.name = name

        if not isinstance(attrs, dict):
            raise TypeError(f"{attrs} has type '{type(attrs).__name__}', expected 'dict'")
        for attr, value in attrs.items():
            setattr(node, attr, value)

        if not isinstance(inputs, dict):
            raise TypeError(f"{inputs} has type '{type(inputs).__name__}', expected 'dict'")
        for input_index, value in inputs.items():
            if isinstance(value, tuple):
                from_node, output_index = value
                links.new(nodes[from_node].outputs[output_index], node.inputs[input_index])
            else:
                node.inputs[input_index].default_value = value

class CustomNodetreeNodeBase:
    def init_node_tree(self, inputs_def, nodes_def, outputs_def):
        node_tree = bpy.data.node_groups.new(self.__class__.__name__, "ShaderNodeTree")
        nodes = node_tree.nodes
        links = node_tree.links

        node_input = nodes.new("NodeGroupInput")
        node_input.name = "inputs"
        for name, (input_type, attrs) in inputs_def.items():
            node_tree.inputs.new(input_type, name)

            if not isinstance(attrs, dict):
                raise TypeError(f"{attrs} has type '{type(attrs).__name__}', expected 'dict'")
            for attribute, value in attrs.items():
                setattr(node_tree.inputs[name], attribute, value)

        setup_node_tree(node_tree, nodes_def)

        node_output = nodes.new("NodeGroupOutput")
        for name, (output_type, attrs, value) in outputs_def.items():
            node_tree.outputs.new(output_type, name)

            if not isinstance(attrs, dict):
                raise TypeError(f"{attrs} has type '{type(attrs).__name__}', expected 'dict'")
            for attribute, value in attrs.items():
                setattr(node_tree.outputs[name], attribute, value)

            if isinstance(value, tuple):
                from_node, output_index = value
                links.new(nodes[from_node].outputs[output_index], node_output.inputs[name])
            else:
                node_output.inputs[name].default_value = value

        self.node_tree = node_tree
        return self.node_tree

    def copy(self, node):
        self.node_tree = node.node_tree.copy()

    def free(self):
        if not self.node_tree.users > 1:
            bpy.data.node_groups.remove(self.node_tree)

    def draw_buttons(self, context, layout):
        for prop in self.bl_rna.properties:
            if prop.is_runtime and not prop.is_readonly:
                text = "" if prop.type == "ENUM" else prop.name
                layout.prop(self, prop.identifier, text=text)

def register_node_category(identifier, category):
    def draw_node_item(self, context):
        layout = self.layout
        col = layout.column(align=True)
        for item in self.category.items(context):
            item.draw(item, col, context)

    menu_type = type("NODE_MT_category_" + category.identifier, (bpy.types.Menu,), {
        "bl_space_type": 'NODE_EDITOR',
        "bl_label": category.name,
        "category": category,
        "poll": category.poll,
        "draw": draw_node_item,
    })

    bpy.utils.register_class(menu_type)

    nodeitems_utils._node_categories[identifier][0].append(category)
    nodeitems_utils._node_categories[identifier][2].append(menu_type)

def unregister_node_category(identifier, category):
    categories = nodeitems_utils._node_categories[identifier][0]
    menu_types = nodeitems_utils._node_categories[identifier][2]

    menu_type = menu_types[categories.index(category)]
    bpy.utils.unregister_class(menu_type)

    categories.remove(category)
    menu_types.remove(menu_type)
