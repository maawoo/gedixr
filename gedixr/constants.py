ALLOWED_PRODUCTS = ['L2A', 'L2B']
PATTERN_L2A = '*GEDI02_A_*.h5'
PATTERN_L2B = '*GEDI02_B_*.h5'

POWER_BEAMS = ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']
COVERAGE_BEAMS = ['BEAM0000', 'BEAM0001', 'BEAM0010', 'BEAM0011']

DEFAULT_VARIABLES = {'L2A': [('rh98', 'rh98')],
                     'L2B': [('tcc', 'cover'),
                             ('fhd', 'fhd_normal'),
                             ('pai', 'pai'),
                             ('rh100', 'rh100')]
                     }

DEFAULT_BASE = {'L2A': [('shot', 'shot_number'),
                        ('latitude', 'lat_lowestmode'),
                        ('longitude', 'lon_lowestmode'),
                        ('elev', 'elev_lowestmode'),
                        ('elev_dem_tdx', 'digital_elevation_model'),
                        ('degrade_flag', 'degrade_flag'),
                        ('quality_flag', 'quality_flag'),
                        ('sensitivity', 'sensitivity'),
                        ('num_detectedmodes', 'num_detectedmodes')],
                'L2B': [('shot', 'shot_number'),
                        ('latitude', 'geolocation/lat_lowestmode'),
                        ('longitude', 'geolocation/lon_lowestmode'),
                        ('elev', 'geolocation/elev_lowestmode'),
                        ('elev_dem_tdx', 'geolocation/digital_elevation_model'),
                        ('degrade_flag', 'geolocation/degrade_flag'),
                        ('quality_flag', 'l2b_quality_flag'),
                        ('sensitivity', 'sensitivity'),
                        ('num_detectedmodes', 'num_detectedmodes')]
                 }
