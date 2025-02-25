#include <mpi.h>
#include <iostream>
#include <thread>
#include <chrono>

int main(int argc, char** argv) {
    int counter = 0;
    int rank, size;
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    if (size < 2) {
        if (rank == 0)
            std::cerr << "At least 2 ranks are required!" << std::endl;
        return 1;
    }
    // Count and send to next rank
    if (rank == 0) {
        MPI_Send(&counter, /* count */ 1, MPI_INT, (rank + 1) % size, /* tag */ 0, MPI_COMM_WORLD);
    }
    while (true) {
        MPI_Recv(&counter, /* count */ 1, MPI_INT, (rank + size - 1) % size, /* tag */ 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        counter++;
        std::this_thread::sleep_for(std::chrono::seconds(1));
        std::cout << "Rank #" << rank << ": " << counter << std::endl;
        MPI_Send(&counter, /* count */ 1, MPI_INT, (rank + 1) % size, /* tag */ 0, MPI_COMM_WORLD);
    }
    MPI_Finalize();
    return 0;
}
