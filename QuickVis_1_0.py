bl_info = {
    "name": "QuickVis",
    "author": "Kyokaz, Claude",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > QuickVis",
    "description": "Easy setup for visibility drivers with custom properties",
    "category": "Animation",
}

import bpy
from bpy.props import StringProperty, EnumProperty, BoolProperty, PointerProperty, IntProperty
from bpy.types import Panel, Operator, PropertyGroup

class VisibilityDriverProperties(PropertyGroup):
    """Properties for the visibility driver addon"""
    
    # Property name for the custom property
    property_name: StringProperty(
        name="Name",
        description="Name of the custom property to control visibility",
        default="visible"
    )
    
    # Property type selection
    property_type: EnumProperty(
        name="Type",
        description="Type of custom property to create",
        items=[
            ('BOOL', "Boolean", "True/False toggle property"),
            ('INT', "Integer", "Integer property limited to 0 or 1"),
        ],
        default='BOOL'
    )
    
    # Where to place the custom property
    property_location: EnumProperty(
        name="Location",
        description="Where to create/use the custom property",
        items=[
            ('SELECTED', "Selected Object", "Use the selected object for custom property"),
            ('EMPTY', "New Empty", "Create a new empty object for custom properties"),
            ('EXISTING', "Existing Object", "Use an existing object for custom property"),
        ],
        default='SELECTED'
    )
    
    # Existing object to use for custom property
    existing_object: PointerProperty(
        name="Existing Object",
        description="Object to use for custom property",
        type=bpy.types.Object
    )
    
    # Default visibility state
    default_visible: BoolProperty(
        name="Default Visible",
        description="Default visibility state",
        default=True
    )
    
    # Visibility value for multiple objects (now limited to 0 or 1)
    visibility_value: IntProperty(
        name="Visibility Value",
        description="The specific value when this object should be visible (0 or 1)",
        default=1,
        min=0,
        max=1
    )


class VISDRIVER_OT_add_visibility_driver(Operator):
    """Add visibility driver to selected objects"""
    bl_idname = "visdriver.add_visibility_driver"
    bl_label = "Add Visibility Driver"
    bl_description = "Add visibility driver to selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.visibility_driver_props
        selected_objects = context.selected_objects
        
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Determine the property holder object
        property_holder = self.get_property_holder(context, props)
        if not property_holder:
            return {'CANCELLED'}
        
        # Only create the property if it doesn't exist
        property_exists = props.property_name in property_holder
        
        if not property_exists:
            if props.property_type == 'BOOL':
                # Set initial value to True for boolean properties
                property_holder[props.property_name] = True
                # Set up the custom property UI for boolean
                try:
                    property_holder.id_properties_ui(props.property_name).update(
                        description=f"Controls visibility of objects (Boolean)",
                        default=True,
                        subtype='NONE'  # This helps with boolean display
                    )
                    # Override the RNA to ensure it's treated as boolean
                    property_holder.property_overridable_library_set(f'["{props.property_name}"]', True)
                except:
                    # Fallback if id_properties_ui doesn't work
                    pass
            else:  # INT (0/1 only)
                # For integer properties, we need to be more explicit about the range
                # First set the value
                property_holder[props.property_name] = 1
                
                # Force update to ensure property is registered
                bpy.context.view_layer.update()
                property_holder.update_tag()
                
                # Now set up the UI limits with both hard and soft limits
                try:
                    ui_data = property_holder.id_properties_ui(props.property_name)
                    ui_data.update(
                        description="Controls visibility of objects (Integer)",
                        default=1,
                        min=0,
                        max=1,
                        soft_min=0,
                        soft_max=1,
                        step=1,
                        precision=0
                    )
                    
                    # Additional force update after setting UI
                    bpy.context.view_layer.update()
                    
                except Exception as e:
                    print(f"Error setting up integer property UI: {e}")
                    # Fallback: try to recreate the property with explicit range
                    try:
                        # Remove and recreate to ensure proper limits
                        current_value = property_holder[props.property_name]
                        del property_holder[props.property_name]
                        property_holder[props.property_name] = current_value
                        
                        # Try setting UI again
                        property_holder.id_properties_ui(props.property_name).update(
                            min=0, max=1, soft_min=0, soft_max=1
                        )
                    except:
                        pass
        
        # Force multiple updates to ensure property is registered
        bpy.context.view_layer.update()
        property_holder.update_tag()
        bpy.context.evaluated_depsgraph_get().update()
        
        # Force UI update
        if bpy.context.area:
            bpy.context.area.tag_redraw()
        
        # Add drivers to selected objects
        added_count = 0
        for obj in selected_objects:
            # Only skip the property holder if we have multiple objects selected
            # and we're using the selected object as property holder
            if (obj == property_holder and 
                props.property_location == 'SELECTED' and 
                len(selected_objects) > 1):
                continue
                
            success = self.add_driver_to_object(obj, property_holder, props)
            if success:
                added_count += 1
        
        if added_count > 0:
            self.report({'INFO'}, f"Added visibility drivers to {added_count} object(s)")
        else:
            self.report({'WARNING'}, "No drivers were added")
        
        return {'FINISHED'}
    
    def get_property_holder(self, context, props):
        """Get the object that will hold the custom property"""
        if props.property_location == 'SELECTED':
            if context.active_object:
                return context.active_object
            else:
                self.report({'WARNING'}, "No active object selected")
                return None
                
        elif props.property_location == 'EMPTY':
            # Create a new empty object
            bpy.ops.object.empty_add(type='PLAIN_AXES')
            empty = context.active_object
            empty.name = f"Visibility_Controller_{props.property_name}"
            return empty
            
        elif props.property_location == 'EXISTING':
            if props.existing_object:
                # Make sure the existing object is accessible
                if props.existing_object.name in bpy.data.objects:
                    return props.existing_object
                else:
                    self.report({'WARNING'}, "Existing object no longer exists")
                    return None
            else:
                self.report({'WARNING'}, "No existing object specified")
                return None
        
        return None
    
    def add_driver_to_object(self, obj, property_holder, props):
        """Add visibility driver to an object"""
        try:
            # Ensure property exists and is accessible
            if props.property_name not in property_holder:
                self.report({'ERROR'}, f"Property '{props.property_name}' not found on {property_holder.name}")
                return False
            
            # Force property holder update
            property_holder.update_tag()
            
            # Remove existing driver if it exists
            if obj.animation_data and obj.animation_data.drivers:
                for driver in obj.animation_data.drivers:
                    if driver.data_path == "hide_viewport":
                        obj.animation_data.drivers.remove(driver)
                        break
            
            # Add new driver for viewport visibility
            driver = obj.driver_add("hide_viewport")
            
            # Set up the driver based on property type and default visible setting
            driver.driver.type = 'SCRIPTED'
            
            if props.property_type == 'BOOL':
                if props.default_visible:
                    # Object visible when property is True
                    driver.driver.expression = f"not {props.property_name}"
                else:
                    # Object visible when property is False (inverted behavior)
                    driver.driver.expression = f"{props.property_name}"
            else:  # INT (0/1 only)
                # For integer properties, use exact value matching for multiple objects
                driver.driver.expression = f"not ({props.property_name} == {props.visibility_value})"
            
            # Add variable
            var = driver.driver.variables.new()
            var.name = props.property_name
            var.type = 'SINGLE_PROP'
            
            # Set up the variable target
            target = var.targets[0]
            target.id = property_holder
            target.data_path = f'["{props.property_name}"]'
            
            # Remove existing render driver if it exists
            if obj.animation_data and obj.animation_data.drivers:
                for driver_render in obj.animation_data.drivers:
                    if driver_render.data_path == "hide_render":
                        obj.animation_data.drivers.remove(driver_render)
                        break
            
            # Also add driver for render visibility with same logic
            driver_render = obj.driver_add("hide_render")
            driver_render.driver.type = 'SCRIPTED'
            
            if props.property_type == 'BOOL':
                if props.default_visible:
                    # Object visible when property is True
                    driver_render.driver.expression = f"not {props.property_name}"
                else:
                    # Object visible when property is False (inverted behavior)
                    driver_render.driver.expression = f"{props.property_name}"
            else:  # INT (0/1 only)
                # For integer properties, use exact value matching for multiple objects
                driver_render.driver.expression = f"not ({props.property_name} == {props.visibility_value})"
            
            var_render = driver_render.driver.variables.new()
            var_render.name = props.property_name
            var_render.type = 'SINGLE_PROP'
            
            target_render = var_render.targets[0]
            target_render.id = property_holder
            target_render.data_path = f'["{props.property_name}"]'
            
            # Force multiple updates to ensure everything is connected
            bpy.context.view_layer.update()
            obj.update_tag()
            property_holder.update_tag()
            
            # Force depsgraph update
            bpy.context.evaluated_depsgraph_get().update()
            
            # Additional update to ensure drivers are evaluated
            bpy.context.scene.frame_set(bpy.context.scene.frame_current)
            
            return True
            
        except Exception as e:
            print(f"Error adding driver to {obj.name}: {e}")
            return False


class VISDRIVER_OT_reverse_single_object(Operator):
    """Reverse visibility for a single object by modifying its driver expression"""
    bl_idname = "visdriver.reverse_single_object"
    bl_label = "Reverse Single Object"
    bl_description = "Reverse visibility for this specific object by inverting its driver logic"
    bl_options = {'REGISTER', 'UNDO'}
    
    target_object_name: StringProperty(name="Target Object", default="")
    
    def execute(self, context):
        # Find the target object
        target_obj = bpy.data.objects.get(self.target_object_name)
        
        if not target_obj:
            self.report({'ERROR'}, f"Target object '{self.target_object_name}' not found")
            return {'CANCELLED'}
        
        if not target_obj.animation_data or not target_obj.animation_data.drivers:
            self.report({'ERROR'}, f"No drivers found on {target_obj.name}")
            return {'CANCELLED'}
        
        # Reverse the driver expressions for this object
        reversed_count = 0
        for driver in target_obj.animation_data.drivers:
            if driver.data_path in ["hide_viewport", "hide_render"]:
                if self.reverse_driver_expression(driver):
                    reversed_count += 1
        
        if reversed_count > 0:
            # Force updates
            target_obj.update_tag()
            bpy.context.view_layer.update()
            bpy.context.evaluated_depsgraph_get().update()
            bpy.context.scene.frame_set(bpy.context.scene.frame_current)
            
            self.report({'INFO'}, f"Reversed driver logic for {target_obj.name}")
        else:
            self.report({'WARNING'}, f"No visibility drivers found to reverse on {target_obj.name}")
        
        return {'FINISHED'}
    
    def reverse_driver_expression(self, driver):
        """Reverse the logic of a driver expression"""
        try:
            current_expression = driver.driver.expression
            
            # If expression starts with "not ", remove it
            if current_expression.startswith("not "):
                new_expression = current_expression[4:]  # Remove "not "
            else:
                # Add "not " to the beginning
                new_expression = f"not ({current_expression})"
            
            driver.driver.expression = new_expression
            print(f"Changed expression: '{current_expression}' → '{new_expression}'")
            return True
            
        except Exception as e:
            print(f"Error reversing driver expression: {e}")
            return False


class VISDRIVER_OT_reverse_connected_drivers(Operator):
    """Reverse visibility values for all objects connected to the selected empty's drivers"""
    bl_idname = "visdriver.reverse_connected_drivers"
    bl_label = "Reverse Connected Drivers"
    bl_description = "Reverse visibility values for all objects driven by this empty's custom properties"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        active_obj = context.active_object
        
        if not active_obj:
            self.report({'WARNING'}, "No active object selected")
            return {'CANCELLED'}
        
        # Get all custom properties from the active object
        custom_props = [key for key in active_obj.keys() if not key.startswith('_')]
        
        if not custom_props:
            self.report({'WARNING'}, f"No custom properties found on {active_obj.name}")
            return {'CANCELLED'}
        
        reversed_count = 0
        
        # For each custom property, find connected objects and reverse their values
        for prop_name in custom_props:
            current_value = active_obj[prop_name]
            connected_objects = self.find_objects_driven_by_property(active_obj, prop_name)
            
            if connected_objects:
                reversed_value = self.calculate_reversed_value(active_obj, prop_name, current_value)
                active_obj[prop_name] = reversed_value
                reversed_count += len(connected_objects)
                
                print(f"Reversed property '{prop_name}': {current_value} → {reversed_value}")
                print(f"  Affects {len(connected_objects)} objects: {[obj.name for obj in connected_objects]}")
        
        if reversed_count > 0:
            # Force updates
            active_obj.update_tag()
            bpy.context.view_layer.update()
            bpy.context.evaluated_depsgraph_get().update()
            bpy.context.scene.frame_set(bpy.context.scene.frame_current)
            
            self.report({'INFO'}, f"Reversed visibility for {reversed_count} connected objects")
        else:
            self.report({'WARNING'}, "No objects found connected to this object's custom properties")
        
        return {'FINISHED'}
    
    def find_objects_driven_by_property(self, property_holder, prop_name):
        """Find all objects that have drivers using the specified property"""
        connected_objects = []
        
        for obj in bpy.data.objects:
            if obj.animation_data and obj.animation_data.drivers:
                for driver in obj.animation_data.drivers:
                    if driver.data_path in ["hide_viewport", "hide_render"]:
                        # Check if this driver uses our property
                        for var in driver.driver.variables:
                            if (var.name == prop_name and 
                                len(var.targets) > 0 and 
                                var.targets[0].id == property_holder):
                                if obj not in connected_objects:
                                    connected_objects.append(obj)
                                break
        
        return connected_objects
    
    def find_what_drives_object(self, obj):
        """Find what properties drive this object's visibility"""
        driving_info = []
        
        if obj.animation_data and obj.animation_data.drivers:
            for driver in obj.animation_data.drivers:
                if driver.data_path in ["hide_viewport", "hide_render"]:
                    for var in driver.driver.variables:
                        if len(var.targets) > 0 and var.targets[0].id:
                            property_holder = var.targets[0].id
                            property_name = var.name
                            
                            # Check if this combination is already in our list
                            existing = next((info for info in driving_info 
                                           if info['holder'] == property_holder and 
                                              info['property'] == property_name), None)
                            if not existing:
                                driving_info.append({
                                    'holder': property_holder,
                                    'property': property_name
                                })
        
        return driving_info
    
    def calculate_reversed_value(self, property_holder, prop_name, current_value):
        """Calculate the reversed value for a property"""
        try:
            if isinstance(current_value, bool):
                # Boolean: just flip True/False
                return not current_value
            elif isinstance(current_value, int):
                # Integer (0/1 only): simple flip
                return 1 if current_value == 0 else 0
            else:
                # Fallback for other types
                if current_value == 0:
                    return 1
                else:
                    return 0
                
        except Exception as e:
            print(f"Error calculating reversed value: {e}")
            # Fallback: simple boolean flip
            if isinstance(current_value, bool):
                return not current_value
            elif current_value == 0:
                return 1
            else:
                return 0


class VISDRIVER_OT_remove_custom_property(Operator):
    """Remove a custom property from an object"""
    bl_idname = "visdriver.remove_custom_property"
    bl_label = "Remove Custom Property"
    bl_description = "Remove the custom property from the object"
    bl_options = {'REGISTER', 'UNDO'}
    
    object_name: StringProperty(name="Object Name", default="")
    property_name: StringProperty(name="Property Name", default="")
    
    @classmethod
    def poll(cls, context):
        return True
    
    def invoke(self, context, event):
        # Show confirmation dialog
        return context.window_manager.invoke_confirm(self, event)
    
    def execute(self, context):
        # Debug output
        print(f"Attempting to remove property: '{self.property_name}' from object: '{self.object_name}'")
        
        if not self.object_name or not self.property_name:
            self.report({'ERROR'}, "Object name and property name required")
            return {'CANCELLED'}
            
        # Find the object
        target_object = bpy.data.objects.get(self.object_name)
        if not target_object:
            self.report({'ERROR'}, f"Object '{self.object_name}' not found")
            return {'CANCELLED'}
        
        # Debug: show what properties exist
        existing_props = [key for key in target_object.keys() if not key.startswith('_')]
        print(f"Existing properties on {self.object_name}: {existing_props}")
        
        # Check if property exists
        if self.property_name not in target_object:
            self.report({'WARNING'}, f"Property '{self.property_name}' not found on {self.object_name}. Available: {existing_props}")
            return {'CANCELLED'}
        
        # Remove the custom property
        del target_object[self.property_name]
        
        # Force updates
        target_object.update_tag()
        bpy.context.view_layer.update()
        
        # Force UI update
        for area in bpy.context.screen.areas:
            area.tag_redraw()
        
        self.report({'INFO'}, f"Removed property '{self.property_name}' from {self.object_name}")
        return {'FINISHED'}


class VISDRIVER_OT_remove_visibility_driver(Operator):
    """Remove visibility driver from selected objects"""
    bl_idname = "visdriver.remove_visibility_driver"
    bl_label = "Remove Visibility Driver"
    bl_description = "Remove visibility driver from selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_objects = context.selected_objects
        
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        removed_count = 0
        for obj in selected_objects:
            if self.remove_driver_from_object(obj):
                removed_count += 1
        
        if removed_count > 0:
            self.report({'INFO'}, f"Removed visibility drivers from {removed_count} object(s)")
        else:
            self.report({'WARNING'}, "No drivers were removed")
        
        return {'FINISHED'}
    
    def remove_driver_from_object(self, obj):
        """Remove visibility driver from an object"""
        try:
            removed = False
            if obj.animation_data and obj.animation_data.drivers:
                drivers_to_remove = []
                for driver in obj.animation_data.drivers:
                    if driver.data_path in ["hide_viewport", "hide_render"]:
                        drivers_to_remove.append(driver)
                
                for driver in drivers_to_remove:
                    obj.animation_data.drivers.remove(driver)
                    removed = True
            
            return removed
            
        except Exception as e:
            print(f"Error removing driver from {obj.name}: {e}")
            return False


class VISDRIVER_PT_main_panel(Panel):
    """Main panel for visibility driver setup"""
    bl_label = "QuickVis"
    bl_idname = "VISDRIVER_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QuickVis"
    
    def find_connected_objects(self, property_holder, prop_name):
        """Find all objects that have drivers using the specified property"""
        connected_objects = []
        
        for obj in bpy.data.objects:
            if obj.animation_data and obj.animation_data.drivers:
                for driver in obj.animation_data.drivers:
                    if driver.data_path in ["hide_viewport", "hide_render"]:
                        # Check if this driver uses our property
                        for var in driver.driver.variables:
                            if (var.name == prop_name and 
                                len(var.targets) > 0 and 
                                var.targets[0].id == property_holder):
                                if obj not in connected_objects:
                                    connected_objects.append(obj)
                                break
        
        return connected_objects
    
    def find_what_drives_object(self, obj):
        """Find what properties drive this object's visibility"""
        driving_info = []
        
        if obj.animation_data and obj.animation_data.drivers:
            for driver in obj.animation_data.drivers:
                if driver.data_path in ["hide_viewport", "hide_render"]:
                    for var in driver.driver.variables:
                        if len(var.targets) > 0 and var.targets[0].id:
                            property_holder = var.targets[0].id
                            property_name = var.name
                            
                            # Check if this combination is already in our list
                            existing = next((info for info in driving_info 
                                           if info['holder'] == property_holder and 
                                              info['property'] == property_name), None)
                            if not existing:
                                driving_info.append({
                                    'holder': property_holder,
                                    'property': property_name
                                })
        
        return driving_info
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.visibility_driver_props
        
        # Property settings
        box = layout.box()
        box.label(text="Property Settings:", icon='PROPERTIES')
        
        box.prop(props, "property_name")
        box.prop(props, "property_type")
        box.prop(props, "property_location")
        
        if props.property_location == 'EXISTING':
            box.prop(props, "existing_object")
        
        box.prop(props, "default_visible")
        
        # Show visibility value for integer properties
        if props.property_type == 'INT':
            box.prop(props, "visibility_value")
            info_box = box.box()
            info_box.scale_y = 0.8
            info_box.label(text="Object visible when property = this value", icon='INFO')
        
        # Actions
        layout.separator()
        
        col = layout.column(align=True)
        col.scale_y = 1.2
        
        # Check if objects are selected
        selected_count = len(context.selected_objects)
        if selected_count > 0:
            col.operator("visdriver.add_visibility_driver", 
                        text=f"Add Vis Driver ({selected_count} obj)", 
                        icon='DRIVER')
        else:
            col.operator("visdriver.add_visibility_driver", 
                        text="Add Vis Driver (No Selection)", 
                        icon='DRIVER')
        
        col.operator("visdriver.remove_visibility_driver", 
                    text="Remove Vis Driver", 
                    icon='X')
        
        # Driver reverse section
        if context.active_object:
            # Check if active object has custom properties that might be driving other objects
            custom_props = [key for key in context.active_object.keys() if not key.startswith('_')] if hasattr(context.active_object, 'keys') else []
            
            if custom_props:
                layout.separator()
                box = layout.box()
                box.label(text="Driver Control:", icon='DRIVER')
                
                # Show connected objects for each property
                total_connected = 0
                for prop_name in custom_props:
                    connected_objects = self.find_connected_objects(context.active_object, prop_name)
                    total_connected += len(connected_objects)
                    
                    if connected_objects:
                        # Property header with current value
                        prop_box = box.box()
                        header_row = prop_box.row()
                        current_value = context.active_object[prop_name]
                        header_row.label(text=f"'{prop_name}' = {current_value}", icon='PROPERTIES')
                        
                        # List connected objects
                        for obj in connected_objects:
                            obj_row = prop_box.row(align=True)
                            obj_row.label(text=f"  {obj.name}", icon='OBJECT_DATA')
                            
                            # Individual reverse button
                            op = obj_row.operator("visdriver.reverse_single_object", text="", icon='FILE_REFRESH')
                            op.target_object_name = obj.name
                
                if total_connected > 0:
                    # Global reverse button
                    row = box.row()
                    row.scale_y = 1.2
                    row.operator("visdriver.reverse_connected_drivers", 
                               text=f"Reverse All ({total_connected} obj)", 
                               icon='FILE_REFRESH')
                else:
                    box.label(text="No connected objects found", icon='ERROR')
            
            # Check if active object is driven by something else
            driving_info = self.find_what_drives_object(context.active_object)
            if driving_info:
                layout.separator()
                box = layout.box()
                box.label(text="This Object is Driven by:", icon='CONSTRAINT')
                
                for info in driving_info:
                    row = box.row(align=True)
                    row.label(text=f"{info['holder'].name}.{info['property']}", icon='PROPERTIES')
                    
                    # Reverse button for this object specifically
                    op = row.operator("visdriver.reverse_single_object", text="", icon='FILE_REFRESH')
                    op.target_object_name = context.active_object.name
        
        # Info section
        layout.separator()
        
        if context.active_object:
            box = layout.box()
            box.label(text="Active Object:", icon='OBJECT_DATA')
            row = box.row()
            row.label(text=context.active_object.name)
            
            # Show custom properties if any
            if hasattr(context.active_object, 'keys') and context.active_object.keys():
                box.label(text="Custom Properties:", icon='PROPERTIES')
                for key in context.active_object.keys():
                    if not key.startswith('_'):
                        row = box.row(align=True)
                        
                        # Check if this is a boolean property (True/False values)
                        value = context.active_object[key]
                        if isinstance(value, bool):
                            # Force boolean display - no slider
                            row.prop(context.active_object, f'["{key}"]', text=key, toggle=True)
                        elif isinstance(value, int) and value in [0, 1]:
                            # Integer property limited to 0/1 - display as checkbox-like
                            row.prop(context.active_object, f'["{key}"]', text=key, slider=False)
                        else:
                            # Standard property
                            row.prop(context.active_object, f'["{key}"]', text=key)
                        
                        # Add remove button with proper property assignment
                        op = row.operator("visdriver.remove_custom_property", text="", icon='X')
                        op.object_name = context.active_object.name
                        op.property_name = key
        
        # Show property holder info if different from active object
        props = context.scene.visibility_driver_props
        if props.property_location == 'EXISTING' and props.existing_object:
            if props.existing_object != context.active_object:
                box = layout.box()
                box.label(text="Property Holder:", icon='PROPERTIES')
                row = box.row()
                row.label(text=props.existing_object.name)
                
                # Show custom properties
                if hasattr(props.existing_object, 'keys') and props.existing_object.keys():
                    for key in props.existing_object.keys():
                        if not key.startswith('_'):
                            row = box.row(align=True)
                            
                            # Check if this is a boolean property
                            value = props.existing_object[key]
                            if isinstance(value, bool):
                                row.prop(props.existing_object, f'["{key}"]', text=key, toggle=True)
                            elif isinstance(value, int) and value in [0, 1]:
                                row.prop(props.existing_object, f'["{key}"]', text=key, slider=False)
                            else:
                                row.prop(props.existing_object, f'["{key}"]', text=key)
                            
                            # Add remove button with proper property assignment
                            op = row.operator("visdriver.remove_custom_property", text="", icon='X')
                            op.object_name = props.existing_object.name
                            op.property_name = key
    
    def find_connected_objects(self, property_holder, prop_name):
        """Find all objects that have drivers using the specified property"""
        connected_objects = []
        
        for obj in bpy.data.objects:
            if obj.animation_data and obj.animation_data.drivers:
                for driver in obj.animation_data.drivers:
                    if driver.data_path in ["hide_viewport", "hide_render"]:
                        # Check if this driver uses our property
                        for var in driver.driver.variables:
                            if (var.name == prop_name and 
                                len(var.targets) > 0 and 
                                var.targets[0].id == property_holder):
                                if obj not in connected_objects:
                                    connected_objects.append(obj)
                                break
        
        return connected_objects


# Registration
classes = (
    VisibilityDriverProperties,
    VISDRIVER_OT_add_visibility_driver,
    VISDRIVER_OT_reverse_single_object,
    VISDRIVER_OT_reverse_connected_drivers,
    VISDRIVER_OT_remove_custom_property,
    VISDRIVER_OT_remove_visibility_driver,
    VISDRIVER_PT_main_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.visibility_driver_props = PointerProperty(
        type=VisibilityDriverProperties
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.visibility_driver_props

if __name__ == "__main__":
    register()
