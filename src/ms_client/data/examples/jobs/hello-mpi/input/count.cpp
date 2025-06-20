#include <mpi.h>
#include <iostream>
#include <thread>
#include <chrono>

int main(int argc, char **argv)
{
    int counter = 0;
    int rank, size;
    char cpu_name[MPI_MAX_PROCESSOR_NAME];
    int cpu_name_len;
    const int max_count = 20;
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Get_processor_name(cpu_name, &cpu_name_len);
    if (size < 2)
    {
        if (rank == 0)
            std::cerr << "At least 2 ranks are required!" << std::endl;
        return 1;
    }
    // Count and send to next rank
    if (rank == 0)
    {
        std::cout << "MPI-size: " << size << std::endl;
        counter++;
        MPI_Send(&counter, /* count */ 1, MPI_INT, (rank + 1) % size, /* tag */ 0, MPI_COMM_WORLD);
    }
    while (true)
    {
        MPI_Recv(&counter, /* count */ 1, MPI_INT, MPI_ANY_SOURCE, /* tag */ 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        if (counter < 0)
            break;
        std::this_thread::sleep_for(std::chrono::seconds(1));
        std::cout << "Rank #" << rank << " received: " << counter << std::endl;
        if (counter < max_count)
        {
            counter++;
            MPI_Send(&counter, /* count */ 1, MPI_INT, (rank + 1) % size, /* tag */ 0, MPI_COMM_WORLD);
        }
        else
        {
            counter = -1;
            for (int i = 0; i < size; i++)
            {
                if (i == rank)
                    continue;
                MPI_Send(&counter, /* count */ 1, MPI_INT, i, /* tag */ 0, MPI_COMM_WORLD);
            }
            break;
        }
    }
    std::cout << "Rank #" << rank << " on " << cpu_name << " shutting down" << std::endl;
    MPI_Finalize();
    return 0;
}