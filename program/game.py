import copy
import time
import Tools as tools


import config.config as config
import config.internal_strings as internal_strings
import config.strings as strings

import program.misc.exceptions as exceptions
import program.misc.helpers as helpers
import program.misc.sdl as sdl
import program.entities as entities
import program.tiles as tiles


class TileData(object):
    """Holds all the Tiles used in a map."""
    def __init__(self):
        self._tile_data = None  # The actual
        self.areas = None
        
    def __getitem__(self, item):
        """Get a single tile.

        :tools.Object item: Should have x, y, z attributes."""
        return self._tile_data[item.z, item.y, item.x]

    def __iter__(self):
        """Iterates over all tiles. Yields a tools.Object with x, y, z, tile, y_row, z_level attributes."""
        for z, z_level in enumerate(self._tile_data):
            for y, y_row in enumerate(z_level):
                for x, tile in enumerate(y_row):
                    yield tools.Object(x=x, y=y, z=z, tile=tile, y_row=y_row, z_level=z_level)
        
    def load(self, tile_data):
        """Sets the tile data from the loaded tile data."""
        self._tile_data = tools.qlist()
        self.areas = []
        for z, data_z_level in enumerate(tile_data):
            self._tile_data.append(tools.qlist())
            max_x = 0
            for y, data_y_row in enumerate(data_z_level):
                self._tile_data[z].append(tools.qlist())
                for x, single_tile_data in enumerate(data_y_row):
                    tile = tiles.Tile(pos=tools.Object(z=z, y=y, x=x))
                    tile.set_from_data(single_tile_data)
                    self._tile_data[z][y].append(tile)
                max_x = max(max_x, x)
            self.areas.append(tools.Object(x=max_x, y=y))
        self.convert_walls()
                        
    def convert_walls(self):
        """Customises the visuals of all the walls based on adjacent walls."""
        for tile_data in self:
            if tile_data.tile.wall:
                adj_tiles = (tile_data.z_level[tile_data.y + i][tile_data.x + j]
                             for i, j in ((-1, 0), (1, 0), (0, -1), (0, 1)))
                adj_directions = (internal_strings.WallAdjacency.DOWN, internal_strings.WallAdjacency.UP,
                                  internal_strings.WallAdjacency.RIGHT, internal_strings.WallAdjacency.LEFT)
                for adj_tile, adj_direction in zip(adj_tiles, adj_directions):
                    if adj_tile.wall:
                        adj_tile.adjacent_walls.add(adj_direction)

        for tile_data in self:
            if tile_data.tile.wall:
                tile_data.tile.convert_wall()
                        
    def level(self, z_level):
        """Gets a z level slice of the tile data."""
        return self._tile_data[z_level]
        
    
class Map(helpers.NameMixin):
    """Holds all map data - the tiles that make up the map, plus associated information such as the map's name, its
    visual depiction on the screen, etc."""
    
    def __init__(self, background_color):
        self.tile_data = TileData()  # The tiles that make up the map
        self.screens = None  # The visual depiction of the map
        self.background_color = background_color  # The background color to use where no tile is defined.
        super(Map, self).__init__(name=None)

    def load(self, map_data):
        """Loads the specified map."""
        self.name = map_data.name
        self.tile_data.load(map_data.tile_data)
        self.screens = [sdl.Surface(((area.x + 1) * config.TILE_X, (area.y + 1) * config.TILE_Y))
                        for area in self.tile_data.areas]
        for screen in self.screens:
            screen.fill(self.background_color)
        for tile_data in self.tile_data:
            self.screens[tile_data.z].blit(tile_data.tile.appearance,
                                           (tile_data.x * config.TILE_X, tile_data.y * config.TILE_Y))
                    
    def level(self, z_level):
        """Gets a specified z-level of the map."""
        return self.tile_data.level(z_level)

    @staticmethod
    def rel(pos, direction):
        """Gets a position based on an existing position and a direction."""
        new_pos = copy.deepcopy(pos)
        if direction == internal_strings.Play.UP:
            new_pos.y -= 1
        elif direction == internal_strings.Play.DOWN:
            new_pos.y += 1
        elif direction == internal_strings.Play.LEFT:
            new_pos.x -= 1
        elif direction == internal_strings.Play.RIGHT:
            new_pos.x += 1
        elif direction == internal_strings.Play.VERTICAL_UP:
            new_pos.z += 1
        elif direction == internal_strings.Play.VERTICAL_DOWN:
            new_pos.z -= 1
        else:
            raise exceptions.ProgrammingException(internal_strings.Exceptions.INVALID_DIRECTION.format(direction=direction))
        return new_pos
        
    def fall(self, pos):
        """Whether or not a flightless entity will fall through the specified position.
        
        False means that they will not fall. True means that they will."""
        this_tile = self.tile_data[pos]
        if this_tile.suspend:
            return False
        pos_beneath = self.rel(pos, internal_strings.Play.VERTICAL_DOWN)
        return not(self.tile_data[pos_beneath].ceiling or this_tile.floor)

    
class MazeGame(object):
    """Main game."""
    def __init__(self, maps_access, interface):
        self._maps_access = maps_access  # Access to all the saved maps
        self.out = interface.out  # Output to screen
        self.inp = interface.inp  # Receive input from user
        interface.register_game(self)

        # Immediately redefined in reset()
        # Just defined here for clarity about what instance properties we have
        self.map = None     # The map that the player is on
        self.player = None  # The player. Unsurprisingly.
        self.debug = None   # Whether or not cheaty debug commands can be executed
        
    def reset(self):
        """Resets the game. (But does not start a new one.)"""
        self.map = Map(self.out.overlays.game.background_color)
        self.player = entities.Player()

        # Must reset output before input, as input might wish to feed something to the output as part of its reset.
        # (e.g. the prompt in the debug console)
        self.out.reset()
        self.inp.reset()

        self.debug = False
        
    def start(self):
        """Starts the game."""
        reset = True
        main_menu = True
        map_select = True
        while True:
            try:
                if reset:
                    self.reset()
                    reset = False
                if main_menu:
                    # TODO: Add a main menu!
                    main_menu = False
                if map_select:
                    self._map_select()
                    map_select = False
                self._run()
                break
            except exceptions.CloseException:
                break
            except exceptions.BaseQuitException as e:
                if isinstance(e, exceptions.MapSelectException):
                    map_select = True
                if isinstance(e, exceptions.QuitException):
                    main_menu = True
                if isinstance(e, exceptions.ResetException):
                    reset = True

    def _map_select(self):
        """Gives the menu to select a map."""
        map_names = self._maps_access.setup_and_find_map_names()
        with self._use_interface('menu'):
            self.out.overlays.menu.reset()
            menu_list = self.out.overlays.menu.list(title=strings.MapSelect.TITLE, entry_text=map_names, necessary=True)
            self.out.overlays.menu.submit(strings.MapSelect.SELECT_MAP)
            self.out.flush()
            while True:
                time.sleep(config.TICK_PAUSE)
                menu_results, input_type = self.inp()
                self.out.flush()
                if input_type == internal_strings.InputTypes.MENU:
                    break

            selected_index = menu_results[menu_list]
            map_name = map_names[selected_index]
            map_ = self._maps_access.get_map(map_name)

        # Load map
        self.map.load(map_)

        # Load player
        self.player.set_pos(map_.start_pos)

    def _run(self):
        """The main game loop."""
        with self._use_interface('game'):
            # Information to be carried over to the next tick, if we don't allow input in this one.
            skip = tools.Object(skip=False)
            self.render()
            while True:
                skip = self._tick(skip)
                self.render()

    def _use_interface(self, interface_name):
        """For use in 'with' statements. Enables both the listener and the overlay with the name :interface_name:"""
        return self.out.use(interface_name) + self.inp.use(interface_name)
    
    def _tick(self, skip):
        """A single tick of the game."""
        # First get input from the user / from a skip condition.
        if skip.skip:
            time.sleep(config.SKIP_PAUSE)
            play_inp, input_type = skip.play_inp, skip.input_type
        else:
            time.sleep(config.TICK_PAUSE)
            play_inp, input_type = self.inp()

        skip = tools.Object(skip=False)
        # Then handle the input.
        if input_type == internal_strings.InputTypes.MOVEMENT:
            did_move = self.move_entity(play_inp, self.player)
            if skip.skip and not did_move:
                raise exceptions.ProgrammingException(internal_strings.Exceptions.INVALID_FORCE_MOVE)
            if not self.player.flight and self.map.fall(self.player.pos):
                skip = tools.Object(skip=True, play_inp=internal_strings.Play.VERTICAL_DOWN,
                                    input_type=internal_strings.InputTypes.MOVEMENT)

        elif input_type == internal_strings.InputTypes.NO_INPUT:
            pass
        else:
            raise exceptions.ProgrammingException(internal_strings.Exceptions.INVALID_INPUT_TYPE.format(input=input_type))

        return skip

    def render(self):
        """Outputs the current game state."""
        self.out.overlays.game.reset()
        self.out.overlays.game(self.map.screens[self.player.z])
        self.out.overlays.game(self.player.appearance, (self.player.x * config.TILE_X, self.player.y * config.TILE_Y))
        self.out.flush()
            
    def move_entity(self, direction, entity):
        """Moves the entity in the specified direction.
        
        Returns True/False based on if it was successfully able to move it or not."""
        current_pos = entity.pos
        new_pos = self.map.rel(current_pos, direction)
        old_tile = self.map.tile_data[current_pos]
        new_tile = self.map.tile_data[new_pos]
        
        if isinstance(new_tile, tools.qlist.Eater):
            return False  # If we're trying to move outside the edge of the map
        if new_tile.boundary:
            return False  # Nothing can pass through boundaries
        if new_tile.solid and not entity.incorporeal:
            return False  # Corporeal entities cannot pass through solid barriers
        if direction == internal_strings.Play.VERTICAL_UP:
            if (old_tile.ceiling or new_tile.floor) and not entity.incorporeal:
                return False  # Corporeal entities cannot pass through solid floors and ceilings.
            if not((old_tile.suspend and new_tile.suspend) or entity.flight):
                return False  # Flightless entities require a asuspension to move vertically upwards
        if direction == internal_strings.Play.VERTICAL_DOWN:
            if (old_tile.floor or new_tile.ceiling) and not entity.incorporeal:
                return False  # Corporeal entities cannot pass through solid floors and ceilings.
        entity.set_pos(new_pos)
        return True
