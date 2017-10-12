import copy
import time

import Tools as tools

import Maze.config.config as config
import Maze.config.strings as strings
import Maze.program.misc.exceptions as exceptions
import Maze.program.misc.inputs as inputs
import Maze.program.entities as entities
import Maze.program.tiles as tiles


class TileData(object):
    """Holds all the Tiles."""
    def __init__(self):
        self._tile_data = None
        
    def __getitem__(self, item):
        return self._tile_data[item.z, item.y, item.x]
        
    def load(self, tile_data):
        """Sets the tile data from the loaded tile data."""
        self._tile_data = tools.qlist()
        for z, data_z_level in enumerate(tile_data):
            self._tile_data.append(tools.qlist())
            for y, data_y_row in enumerate(data_z_level):
                self._tile_data[z].append(tools.qlist())
                for x, single_tile_data in enumerate(data_y_row):
                    tile = tiles.Tile(pos=tools.Object(z=z, y=y, x=x))
                    tile.set_from_data(single_tile_data)
                    self._tile_data[z][y].append(tile)
        self.convert_walls()
                        
    def convert_walls(self):
        """Customises the visuals of all the walls based on adjacent walls."""
        for z, tile_level in enumerate(self._tile_data):
            for y, tile_row in enumerate(tile_level):
                for x, tile in enumerate(tile_row):
                    if tile.wall:
                        adj_tiles = (tile_level[y + i][x + j] for i, j in ((-1, 0), (1, 0), (0, -1), (0, 1)))
                        adj_directions = (config.WallAdjacency.DOWN, config.WallAdjacency.UP,
                                          config.WallAdjacency.RIGHT, config.WallAdjacency.LEFT)
                        for adj_tile, adj_direction in zip(adj_tiles, adj_directions):
                            if adj_tile.wall:
                                adj_tile.adjacent_walls.add(adj_direction)
        
        for tile_level in self._tile_data:
            for tile_row in tile_level:
                for tile in tile_row:
                    if tile.wall:
                        tile.convert_wall()
                        
    def level(self, z_level):
        """Gets a z level slice of the tile data."""
        return self._tile_data[z_level]
        
    
class Map(object):
    """Holds all map data."""
    
    def __init__(self):
        self.name = None
        self.tile_data = TileData()

    def load(self, map_data):
        """Loads the specified map."""
        self.name = map_data.name
        self.tile_data.load(map_data.tile_data)
                    
    def level(self, z_level):
        """Gets a specified z-level of the map."""
        return self.tile_data.level(z_level)

    @staticmethod
    def rel(pos, direction):
        """Gets a position based on an existing position and a direction."""
        new_pos = copy.deepcopy(pos)
        if direction == config.Play.UP:
            new_pos.y -= 1
        elif direction == config.Play.DOWN:
            new_pos.y += 1
        elif direction == config.Play.LEFT:
            new_pos.x -= 1
        elif direction == config.Play.RIGHT:
            new_pos.x += 1
        elif direction == config.Play.VERTICAL_UP:
            new_pos.z += 1
        elif direction == config.Play.VERTICAL_DOWN:
            new_pos.z -= 1
        else:
            raise exceptions.ProgrammingException('Unexpected direction "{direction}"'.format(direction=direction))
        return new_pos
        
    def add_entity(self, pos, player):
        """Adds an entity to the tile in the specified position."""
        self.tile_data[pos].add_entity(player)
        
    def remove_entity(self, pos, player):
        """Removes an entity from the tile in the specified position. Will raise an exception if the entity is not
        there."""
        self.tile_data[pos].remove_entity(player)
        
    def fall(self, pos):
        """Whether or not a flightless entity will fall through the specified position.
        
        False means that they will not fall. True means that they will."""
        this_tile = self.tile_data[pos]
        if this_tile.suspend:
            return False
        pos_beneath = self.rel(pos, config.Play.VERTICAL_DOWN)
        return not(self.tile_data[pos_beneath].ceiling or this_tile.floor)

    
class MazeGame(object):
    """Main game."""
    def __init__(self, maps_access, interface):
        self.maps_access = maps_access
        self.out = interface.output
        self.inp = interface.input

        self.map = None     # Immediately redefined in reset()
        self.player = None  # Just defined here for clarity about what instance properties we have
        self.debug = None   #
        self.reset()
        
    def reset(self):
        """Resets the game. (But does not start a new one.)"""
        self.map = Map()
        self.player = entities.Player()

        self.debug = False
        
    def start(self):
        """Starts the game."""
        self.inp.set(config.InputInterfaces.SELECTMAP)
        self.map_select()
        self.inp.set(config.InputInterfaces.PLAY)
        return self._run()
        
    def map_select(self):
        """Gives the menu to select a map."""
        # Map Selection
        map_names = self.maps_access.setup_and_find_map_names()

        # Print the map options
        numbers = [strings.MapSelect.option_number.format(number=i) for i in range(len(map_names))]
        with self.out.debug.no_flush_context():
            self.out.debug.clear()
            self.out.debug.table(title=strings.MapSelect.title, columns=[numbers, map_names], headers=strings.MapSelect.headers)
        
        # Get the selected map option
        while True:
            try:
                inp = self.inp(strings.MapSelect.input, type_arg=int, num_chars=2, end='\n', print_received_input=True)
                map_name = map_names[inp]
            except (ValueError, IndexError):  # Cannot cast to int or number does not correspond to a map
                self.inp.invalid_input()
            else:
                map_ = self.maps_access.get_map(map_name)
                break
        
        # Map
        self.map.load(map_)
        self.map.add_entity(map_.start_pos, self.player)
        
        # Player
        self.player.set_pos(map_.start_pos)

    def _run(self):
        """The main game loop."""
        completed = False
        skip = tools.Object(skip=False)
        self.render()
        while not completed:
            tick_result = self._tick(skip)
            completed = tick_result.completed
            skip = tick_result.skip
            if tick_result.render:
                self.render()
        return tick_result.again
    
    def _tick(self, skip):
        """A single tick of the game."""
        if skip.skip:
            time.sleep(config.SLEEP_SKIP)
            play_inp, is_move = skip.play_inp, skip.is_move
        else:
            play_inp, is_move = self.inp.play_inp()
        if is_move:
            move_result = self.move_entity(play_inp, self.player)
            if skip.skip and not move_result:
                raise exceptions.ProgrammingException('Received an invalid force move command.')
            input_result = tools.Object(completed=False, render=True, progress=True, again=False)
            if not self.player.flight and self.map.fall(self.player.pos):
                input_result.skip = tools.Object(skip=True, play_inp=config.Play.VERTICAL_DOWN, is_move=True)
            else:
                input_result.skip = tools.Object(skip=False)
        else:
            input_ = play_inp.split(' ')
            special_input = inputs.SpecialInput.find_subclass(input_[0])
            inp_args = tools.qlist(input_[1:], except_val='')
            input_result = special_input.do(self, inp_args)
        if input_result.progress:
            # Do stuff
            pass
        return input_result

    def render(self):
        """Outputs the current game state."""
        z_level = self.map.level(self.player.z)
        with self.out.debug.no_flush_context():
            self.out.debug.clear()
            for y, y_row in enumerate(z_level):
                for x, tile in enumerate(y_row):
                    self.out.debug(tile.disp())
                self.out.debug('\n')
            
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
        if direction == config.Play.VERTICAL_UP:
            if (old_tile.ceiling or new_tile.floor) and not entity.incorporeal:
                return False  # Corporeal entities cannot pass through solid floors and ceilings.
            if not((old_tile.suspend and new_tile.suspend) or entity.flight):
                return False  # Flightless entities require a asuspension to move vertically upwards
        if direction == config.Play.VERTICAL_DOWN:
            if (old_tile.floor or new_tile.ceiling) and not entity.incorporeal:
                return False  # Corporeal entities cannot pass through solid floors and ceilings.
                
        self.map.remove_entity(current_pos, entity)
        self.map.add_entity(new_pos, entity)
        entity.set_pos(new_pos)
        return True
