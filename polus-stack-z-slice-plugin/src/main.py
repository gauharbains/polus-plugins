import argparse, logging, math, filepattern, time, queue
from bfio import BioReader, BioWriter
import pathlib
from preadator import ProcessManager

logging.basicConfig(format='%(asctime)s - %(name)-8s - %(levelname)-8s - %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S')

# length/width of the chunk each _merge_layers thread processes at once
chunk_size = 8192

# Units for conversion
UNITS = {'m':  10**9,
         'cm': 10**7,
         'mm': 10**6,
         'µm': 10**3,
         'nm': 1,
         'Å':  10**-1}

def _merge_layers(input_files,output_path):
    
    with ProcessManager.process(output_path.name):

        # Get the number of layers to stack
        z_size = 0
        for f in input_files:
            with BioReader(f['file']) as br:
                z_size += br.z
                
        # Get some basic info about the files to stack
        with BioReader(input_files[0]['file']) as br:

            # Get the physical z-distance if available, set to physical x if not
            ps_z = br.ps_z
            
            # If the z-distances are undefined, average the x and y together
            if None in ps_z:
                # Get the size and units for x and y
                x_val,x_units = br.ps_x
                y_val,y_units = br.ps_y
                
                # Convert x and y values to the same units and average
                z_val = (x_val*UNITS[x_units] + y_val*UNITS[y_units])/2
                
                # Set z units to the smaller of the units between x and y
                z_units = x_units if UNITS[x_units] < UNITS[y_units] else y_units
                
                # Convert z to the proper unit scale
                z_val /= UNITS[z_units]
                ps_z = (z_val,z_units)
                ProcessManager.log('Could not find physical z-size. Using the average of x & y {}.'.format(ps_z))

            # Hold a reference to the metadata once the file gets closed
            metadata = br.metadata

        # Create the output file within a context manager
        with BioWriter(output_path,metadata=metadata,max_workers=ProcessManager._active_threads) as bw:

            # Adjust the dimensions before writing
            bw.z = z_size
            bw.ps_z = ps_z

            # ZIndex tracking for the output file
            zi = 0

            # Start stacking
            for file in input_files:

                # Open an image
                with BioReader(file['file'],max_workers=ProcessManager._active_threads) as br:

                    # Open z-layers one at a time
                    for z in range(br.z):

                        # Use tiled reading in x&y to conserve memory
                        # At most, [chunk_size, chunk_size] pixels are loaded
                        for xs in range(0,br.x,chunk_size):
                            xe = min([br.x,xs + chunk_size])

                            for ys in range(0,br.y,chunk_size):
                                ye = min([br.y,ys + chunk_size])

                                bw[ys:ye,xs:xe,zi:zi+1,...] = br[ys:ye,xs:xe,z:z+1,...]

                        zi += 1

                # update the BioWriter in case the ProcessManager found more threads
                bw.max_workers = ProcessManager._active_threads
                
def main(input_dir: pathlib.Path,
         file_pattern: str,
         output_dir: pathlib.Path
         ) -> None:
    
    # create the filepattern object
    fp = filepattern.FilePattern(input_dir,file_pattern)
    
    for files in fp(group_by='z'):

        output_name = fp.output_name(files)
        output_file = output_dir.joinpath(output_name)

        ProcessManager.submit_process(_merge_layers,files,output_file)
    
    ProcessManager.join_processes()

if __name__ == "__main__":
    # Initialize the main thread logger
    logger = logging.getLogger('main')
    logger.setLevel(logging.INFO)

    # Setup the Argument parsing
    logger.info('Parsing arguments...')
    parser = argparse.ArgumentParser(prog='main', description='Compile individual tiled tiff images into a single volumetric tiled tiff.')

    parser.add_argument('--inpDir', dest='input_dir', type=str,
                        help='Path to folder with tiled tiff files', required=True)
    parser.add_argument('--outDir', dest='output_dir', type=str,
                        help='The output directory for ome.tif files', required=True)
    parser.add_argument('--filePattern', dest='file_pattern', type=str,
                        help='A filename pattern specifying variables in filenames.', required=True)

    args = parser.parse_args()
    input_dir = pathlib.Path(args.input_dir)
    if input_dir.joinpath("images").is_dir():
        input_dir = input_dir.joinpath("images")
    output_dir = pathlib.Path(args.output_dir)
    file_pattern = args.file_pattern
    logger.info(f'input_dir = {input_dir}')
    logger.info(f'output_dir = {output_dir}')
    logger.info(f'file_pattern = {file_pattern}')
    logger.info(f'max_threads: {ProcessManager.num_processes()}')
    
    ProcessManager.init_processes('main','stack')

    main(input_dir,
         file_pattern,
         output_dir)