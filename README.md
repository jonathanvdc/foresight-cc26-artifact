To build Docker image:

```sh
docker build -t foresight-evaluation .
```

To run all experiments:

```sh
docker run --rm -it \
  --mount type=bind,src=./results,dst=/results \
  foresight-evaluation
```
